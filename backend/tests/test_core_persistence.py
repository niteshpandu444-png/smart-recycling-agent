"""
Core persistence, confirmation workflow, Digital Twin snapshot, and event tests.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.database import Base, init_db
from backend.app.models import Scan, MaterialEntry, VirtualBin, MaterialEvent
from backend.app.adapters.event_publisher import clear_event_listeners, register_event_listener
from backend.app.services.material_service import (
    confirm_material,
    ScanNotFoundError,
    ScanAlreadyConfirmedError,
    BinOverflowError,
)
from backend.app.adapters.schemas import MaterialConfirmRequest


def test_database_initialization_and_default_bins(test_db):
    """Verifies tables are created and default baseline bins are populated."""
    bins = test_db.query(VirtualBin).all()
    bin_ids = {b.id for b in bins}
    expected_bins = {
        "bin-plastic",
        "bin-paper",
        "bin-metal",
        "bin-glass",
        "bin-organic",
        "bin-holding",
    }
    assert expected_bins.issubset(bin_ids)
    assert len(bins) >= 6


def test_entity_relationships(test_db, sample_scan):
    """Verifies ORM relationships between Scan, MaterialEntry, and MaterialEvent."""
    req = MaterialConfirmRequest(
        scan_id=sample_scan.id,
        confirmed_category="plastic",
        quantity=2.0,
        unit="items",
    )
    entry = confirm_material(test_db, req)

    # Reload from DB
    scan = test_db.query(Scan).filter(Scan.id == sample_scan.id).first()
    assert scan.material_entry is not None
    assert scan.material_entry.id == entry.id
    assert len(scan.events) == 1
    assert scan.events[0].material_id == entry.id
    assert scan.events[0].destination_bin_id == "bin-plastic"


def test_material_confirmation_flow(client, test_db, sample_scan):
    """Tests full HTTP confirmation flow and verifies inventory updates."""
    # Register listener to test event publisher
    published_events = []
    clear_event_listeners()
    register_event_listener(lambda ev, data: published_events.append((ev, data)))

    bin_before = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    inv_before = bin_before.current_inventory

    payload = {
        "scan_id": sample_scan.id,
        "confirmed_category": "plastic",
        "quantity": 3.0,
        "unit": "items",
        "description": "Clean water bottle",
        "confirmation_source": "user_visual",
    }
    resp = client.post("/api/materials/confirm", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["scan_id"] == sample_scan.id
    assert data["category"] == "plastic"
    assert data["quantity"] == 3.0
    assert data["destination"] == "bin-plastic"
    assert data["confirmation_source"] == "user_visual"

    # Verify inventory was updated
    test_db.expire_all()
    bin_after = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    assert bin_after.current_inventory == inv_before + 3.0

    # Verify scan marked confirmed
    scan_after = test_db.query(Scan).filter(Scan.id == sample_scan.id).first()
    assert scan_after.review_status == "confirmed"

    # Verify event published
    assert len(published_events) == 1
    assert published_events[0][0] == "material_confirmed"
    assert published_events[0][1]["material_id"] == data["id"]


def test_duplicate_confirmation_protection(client, sample_scan):
    """Verifies that confirming an already confirmed scan raises 409 Conflict."""
    payload = {
        "scan_id": sample_scan.id,
        "confirmed_category": "plastic",
        "quantity": 1.0,
    }
    first_resp = client.post("/api/materials/confirm", json=payload)
    assert first_resp.status_code == 201

    # Second attempt without matching idempotency key must raise 409
    second_resp = client.post("/api/materials/confirm", json=payload)
    assert second_resp.status_code == 409
    assert "already been confirmed" in second_resp.json()["detail"]


def test_idempotency_key_replay(client, test_db, sample_scan):
    """Verifies that replaying with Idempotency-Key returns original result without double-counting."""
    headers = {"Idempotency-Key": "idemp-key-12345"}
    payload = {
        "scan_id": sample_scan.id,
        "confirmed_category": "plastic",
        "quantity": 2.0,
    }

    bin_before = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory

    # First request
    resp1 = client.post("/api/materials/confirm", json=payload, headers=headers)
    assert resp1.status_code == 201
    entry_id_1 = resp1.json()["id"]

    # Replay request
    resp2 = client.post("/api/materials/confirm", json=payload, headers=headers)
    assert resp2.status_code == 201
    entry_id_2 = resp2.json()["id"]

    assert entry_id_1 == entry_id_2

    # Inventory must have increased by ONLY 2.0, not 4.0
    test_db.expire_all()
    bin_after = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory
    assert bin_after == bin_before + 2.0


def test_nonexistent_scan_returns_404(client):
    payload = {
        "scan_id": "non-existent-scan-999",
        "confirmed_category": "plastic",
        "quantity": 1.0,
    }
    resp = client.post("/api/materials/confirm", json=payload)
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_invalid_category_returns_422(client, sample_scan):
    payload = {
        "scan_id": sample_scan.id,
        "confirmed_category": "toxic_waste",  # Invalid
        "quantity": 1.0,
    }
    resp = client.post("/api/materials/confirm", json=payload)
    assert resp.status_code == 422


def test_bin_overflow_rejection(client, test_db, sample_scan):
    """Verifies that an item exceeding bin capacity is rejected and not partially added."""
    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    plastic_bin.current_inventory = 95.0
    plastic_bin.capacity = 100.0
    test_db.commit()

    # Try adding 10.0 (95 + 10 = 105 > 100)
    payload = {
        "scan_id": sample_scan.id,
        "confirmed_category": "plastic",
        "quantity": 10.0,
    }
    resp = client.post("/api/materials/confirm", json=payload)
    assert resp.status_code == 400
    assert "capacity exceeded" in resp.json()["detail"].lower()

    # Verify inventory untouched
    test_db.expire_all()
    assert plastic_bin.current_inventory == 95.0
    # Scan remains pending
    assert sample_scan.review_status == "pending"


def test_transaction_rollback_no_websocket_broadcast(test_db, sample_scan):
    """Verifies that if a transaction fails, no partial records exist and no event is broadcast."""
    published_events = []
    clear_event_listeners()
    register_event_listener(lambda ev, data: published_events.append((ev, data)))

    # Overflow error triggers rollback
    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    plastic_bin.capacity = 10.0
    plastic_bin.current_inventory = 9.0
    test_db.commit()

    req = MaterialConfirmRequest(
        scan_id=sample_scan.id,
        confirmed_category="plastic",
        quantity=5.0,  # Overflow
    )

    with pytest.raises(BinOverflowError):
        confirm_material(test_db, req)

    # Check database state: no MaterialEntry, no MaterialEvent, bin inventory unchanged
    assert test_db.query(MaterialEntry).filter(MaterialEntry.scan_id == sample_scan.id).count() == 0
    assert test_db.query(MaterialEvent).filter(MaterialEvent.scan_id == sample_scan.id).count() == 0
    assert plastic_bin.current_inventory == 9.0
    assert len(published_events) == 0


def test_digital_twin_snapshot_endpoint(client, sample_scan):
    # Confirm an item
    client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 4.0},
    )

    resp = client.get("/api/twin/snapshot")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_confirmed_items"] >= 4.0
    assert "plastic" in data["category_inventory"]
    assert data["category_inventory"]["plastic"] >= 4.0
    assert len(data["bins"]) >= 6

    # Verify plastic bin occupancy calculation
    plastic_bin = next(b for b in data["bins"] if b["id"] == "bin-plastic")
    assert plastic_bin["current_inventory"] >= 4.0
    assert plastic_bin["occupancy_percentage"] is not None
    assert plastic_bin["occupancy_percentage"] > 0


def test_events_endpoint_and_pagination(client, test_db, sample_scan):
    # Create a couple of events
    client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 2.0},
    )

    resp = client.get("/api/events?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_count"] >= 1
    assert len(data["items"]) >= 1
    assert data["items"][0]["event_type"] == "confirmed"


def test_persistence_across_restart(tmp_path):
    """Verifies that data written to SQLite persists when a new engine and session connect."""
    db_file = tmp_path / "test_persist.db"
    db_url = f"sqlite:///{db_file}"

    engine1 = create_engine(db_url)
    init_db(target_engine=engine1)
    Session1 = sessionmaker(bind=engine1)
    s1 = Session1()

    scan = Scan(
        id="scan-persistent-1",
        predicted_category="glass",
        confidence=0.99,
    )
    s1.add(scan)
    s1.commit()

    req = MaterialConfirmRequest(
        scan_id="scan-persistent-1",
        confirmed_category="glass",
        quantity=5.0,
    )
    confirm_material(s1, req)
    s1.close()
    engine1.dispose()

    # Restart / reconnect with engine2
    engine2 = create_engine(db_url)
    Session2 = sessionmaker(bind=engine2)
    s2 = Session2()

    saved_entry = s2.query(MaterialEntry).filter(MaterialEntry.scan_id == "scan-persistent-1").first()
    assert saved_entry is not None
    assert saved_entry.quantity == 5.0
    assert saved_entry.destination == "bin-glass"

    glass_bin = s2.query(VirtualBin).filter(VirtualBin.id == "bin-glass").first()
    assert glass_bin.current_inventory == 5.0

    s2.close()
    engine2.dispose()
