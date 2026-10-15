"""
Tests for Phase 3: Digital Twin Features.
Covers what-if simulations, bin lifecycle (empty, transfer), bin CRUD/history,
configurable simulation thresholds, and compensating event reversals.
"""
import pytest
from backend.app.models import VirtualBin, MaterialEntry, MaterialEvent, Scan


def test_what_if_simulation_read_only(client, test_db):
    """
    Verifies that what-if simulation:
    - Calculates projected inventory, occupancy, and overflow warnings.
    - Accurately projects misclassification error impacts.
    - NEVER writes to the database (read-only).
    """
    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    start_inv = plastic_bin.current_inventory
    event_count_before = test_db.query(MaterialEvent).count()

    sim_payload = {
        "hypothetical_additions": [
            {"category": "plastic", "quantity": 50.0},
            {"category": "plastic", "quantity": 60.0},  # Total 110 > 100 capacity
            {"category": "glass", "quantity": 20.0},
        ],
        "hypothetical_misclassification_rates": {
            "bin-plastic": 0.10  # 10% of items misclassified
        },
    }

    resp = client.post("/api/twin/simulate", json=sim_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["simulation_label"] == "HYPOTHETICAL_SIMULATION_READ_ONLY"
    assert len(data["bin_projections"]) >= 2

    # Check plastic projection
    proj_plastic = next(p for p in data["bin_projections"] if p["bin_id"] == "bin-plastic")
    assert proj_plastic["starting_inventory"] == start_inv
    assert proj_plastic["projected_inventory"] == start_inv + 110.0
    assert proj_plastic["would_overflow"] is True
    assert proj_plastic["projected_status"] == "overflow_risk"
    assert proj_plastic["potential_contamination_items"] == 11.0  # 10% of 110

    # CRITICAL: Verify nothing was persisted
    test_db.expire_all()
    assert plastic_bin.current_inventory == start_inv
    assert test_db.query(MaterialEvent).count() == event_count_before


def test_bin_empty_lifecycle_and_processing_totals(client, test_db, sample_scan):
    """
    Verifies that emptying a bin:
    1. Sets inventory to 0.0 and status to 'normal'.
    2. Emits an 'emptied' event.
    3. Accurately reflects in Digital Twin snapshot processing_totals.
    """
    # 1. Add material to plastic bin
    client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 15.0},
    )

    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    assert plastic_bin.current_inventory == 15.0

    # 2. Empty the bin
    empty_resp = client.post("/api/bins/bin-plastic/empty?reason=Scheduled+recycling+pickup")
    assert empty_resp.status_code == 200
    assert empty_resp.json()["current_inventory"] == 0.0

    # 3. Verify event recorded
    emptied_event = (
        test_db.query(MaterialEvent)
        .filter(MaterialEvent.source_bin_id == "bin-plastic", MaterialEvent.event_type == "emptied")
        .first()
    )
    assert emptied_event is not None
    assert emptied_event.quantity == 15.0
    assert emptied_event.payload["reason"] == "Scheduled recycling pickup"

    # 4. Check Digital Twin snapshot processing totals
    snap_resp = client.get("/api/twin/snapshot")
    assert snap_resp.status_code == 200
    snap = snap_resp.json()
    assert "plastic" in snap["processing_totals"]
    assert snap["processing_totals"]["plastic"] >= 15.0


def test_bin_transfer_operation(client, test_db):
    """Verifies atomic transfer between two virtual bins."""
    b_paper = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-paper").first()
    b_holding = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-holding").first()

    b_paper.current_inventory = 25.0
    b_holding.current_inventory = 5.0
    test_db.commit()

    transfer_payload = {
        "from_bin_id": "bin-paper",
        "to_bin_id": "bin-holding",
        "quantity": 10.0,
        "reason": "Secondary sorting inspection",
    }
    resp = client.post("/api/bins/transfer", json=transfer_payload)
    assert resp.status_code == 200

    test_db.expire_all()
    assert b_paper.current_inventory == 15.0
    assert b_holding.current_inventory == 15.0

    # Verify event
    trans_ev = (
        test_db.query(MaterialEvent)
        .filter(MaterialEvent.event_type == "transferred", MaterialEvent.source_bin_id == "bin-paper")
        .first()
    )
    assert trans_ev is not None
    assert trans_ev.quantity == 10.0
    assert trans_ev.destination_bin_id == "bin-holding"


def test_bin_management_crud_and_history(client, test_db):
    """Tests bin creation, listing, patching, and history retrieval."""
    # Create new bin
    create_payload = {
        "id": "bin-electronics",
        "name": "E-Waste Depot",
        "accepted_category": "electronic",
        "capacity": 30.0,
        "inventory_unit": "items",
    }
    create_resp = client.post("/api/bins", json=create_payload)
    assert create_resp.status_code == 201
    assert create_resp.json()["id"] == "bin-electronics"

    # Patch capacity
    patch_resp = client.patch("/api/bins/bin-electronics", json={"capacity": 45.0, "status": "normal"})
    assert patch_resp.status_code == 200
    assert patch_resp.json()["capacity"] == 45.0

    # Get history
    hist_resp = client.get("/api/bins/bin-electronics/history")
    assert hist_resp.status_code == 200
    assert isinstance(hist_resp.json(), list)


def test_simulation_settings_endpoints(client):
    """Verifies configurable simulation thresholds endpoint retrieval and patching."""
    get_resp = client.get("/api/twin/settings")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "settings" in data
    assert data["settings"]["warning_threshold"] == 0.75

    # Update threshold
    patch_resp = client.patch(
        "/api/twin/settings",
        json={"warning_threshold": 0.80, "critical_threshold": 0.95},
    )
    assert patch_resp.status_code == 200

    # Verify updated
    get_after = client.get("/api/twin/settings").json()
    assert get_after["settings"]["warning_threshold"] == 0.80
    assert get_after["settings"]["critical_threshold"] == 0.95


def test_compensating_reversal_event(client, test_db, sample_scan):
    """Verifies that reversing an event restores inventory and preserves audit history."""
    confirm_resp = client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 4.0},
    )
    assert confirm_resp.status_code == 201
    entry_id = confirm_resp.json()["id"]

    # Get the confirmed event
    orig_event = (
        test_db.query(MaterialEvent)
        .filter(MaterialEvent.material_id == entry_id, MaterialEvent.event_type == "confirmed")
        .first()
    )

    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    inv_before_rev = plastic_bin.current_inventory

    # Perform reversal
    rev_resp = client.post(
        f"/api/events/{orig_event.id}/reverse",
        json={"reason": "Item erroneously scanned twice by user"},
    )
    assert rev_resp.status_code == 201
    rev_data = rev_resp.json()
    assert rev_data["event_type"] == "reversal"

    test_db.expire_all()
    # Inventory restored
    assert plastic_bin.current_inventory == inv_before_rev - 4.0

    # Original material marked reversed
    mat = test_db.query(MaterialEntry).filter(MaterialEntry.id == entry_id).first()
    assert mat.processing_status == "reversed"
