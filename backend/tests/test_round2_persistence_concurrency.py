"""
Round 2 Tests: Concurrency Safety, Event Replay, Snapshot History, and Filter Edge Cases.
Uses file-based SQLite databases to thoroughly test multithreaded transaction concurrency.
"""
import concurrent.futures
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models import VirtualBin, Scan, MaterialEntry, MaterialEvent, SnapshotRecord
from backend.app.services.material_service import (
    confirm_material,
    ScanAlreadyConfirmedError,
    BinOverflowError,
)
from backend.app.services.digital_twin_service import (
    get_filtered_events,
    get_snapshot_history,
    record_snapshot_state,
    get_digital_twin_snapshot,
)
from backend.app.services.analytics_service import calculate_fill_rates_and_time_to_full
from backend.app.adapters.schemas import MaterialConfirmRequest
from backend.app.adapters.request_context import get_request_id, sanitize_message
from backend.app.adapters.event_publisher import register_event_listener, clear_event_listeners


@pytest.fixture
def file_db_factory(tmp_path):
    """Creates a real file-based SQLite database with WAL mode for multithreading tests."""
    db_file = tmp_path / "concurrent_test.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False, "timeout": 30.0},
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON;")

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Seed baseline bins
    session = session_factory()
    test_bins = [
        VirtualBin(id="bin-plastic", name="Plastic Bin", accepted_category="plastic", capacity=50.0, current_inventory=0.0),
        VirtualBin(id="bin-holding", name="Holding Bin", accepted_category="holding", capacity=20.0, current_inventory=0.0),
        VirtualBin(id="bin-small", name="Small Capacity Bin", accepted_category="glass", capacity=5.0, current_inventory=0.0),
    ]
    for b in test_bins:
        session.add(b)
    session.commit()
    session.close()

    return session_factory


# ------------------------------------------------------------------------------
# 1. CONCURRENCY SAFETY TESTS (File-based SQLite WAL)
# ------------------------------------------------------------------------------

def test_concurrent_confirmations_of_same_scan_yields_single_entry(file_db_factory):
    """
    Two concurrent worker threads attempting to confirm the exact same scan ID.
    Exactly one must succeed in creating an entry; the other must receive ScanAlreadyConfirmedError.
    Total bin inventory must increment exactly once.
    """
    session = file_db_factory()
    scan_id = str(uuid4())
    scan = Scan(
        id=scan_id,
        predicted_category="plastic",
        confidence=0.95,
        model_identifier="test-model",
        review_status="pending",
    )
    session.add(scan)
    session.commit()
    session.close()

    results = []
    errors = []

    def confirm_worker(worker_id: int):
        worker_session = file_db_factory()
        req = MaterialConfirmRequest(
            scan_id=scan_id,
            confirmed_category="plastic",
            quantity=1.0,
            unit="items",
            confirmation_source="user_confirmed",
        )
        try:
            res = confirm_material(worker_session, req)
            results.append(res.id)
        except ScanAlreadyConfirmedError as e:
            errors.append(type(e).__name__)
        except Exception as e:
            errors.append(f"Unexpected: {type(e).__name__}")
        finally:
            worker_session.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(confirm_worker, i) for i in range(2)]
        concurrent.futures.wait(futures)

    verify_session = file_db_factory()
    entries = verify_session.query(MaterialEntry).filter(MaterialEntry.scan_id == scan_id).all()
    plastic_bin = verify_session.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").one()

    # Exactly 1 success, exactly 1 rejection
    assert len(results) == 1
    assert len(errors) == 1
    assert errors[0] == "ScanAlreadyConfirmedError"
    assert len(entries) == 1
    assert plastic_bin.current_inventory == 1.0
    verify_session.close()


def test_concurrent_confirmations_cannot_exceed_bin_capacity(file_db_factory):
    """
    Bin has capacity 5.0. Two threads concurrently attempt to add 4.0 items each.
    Atomic conditional update must allow only one addition; the second must raise BinOverflowError.
    Final bin inventory must be exactly 4.0, never 8.0.
    """
    session = file_db_factory()
    scan1_id, scan2_id = str(uuid4()), str(uuid4())
    session.add(Scan(id=scan1_id, predicted_category="glass", confidence=0.9, review_status="pending"))
    session.add(Scan(id=scan2_id, predicted_category="glass", confidence=0.9, review_status="pending"))
    session.commit()
    session.close()

    results = []
    overflow_errors = []

    def capacity_worker(scan_id_to_use: str):
        worker_session = file_db_factory()
        req = MaterialConfirmRequest(
            scan_id=scan_id_to_use,
            confirmed_category="glass",
            quantity=4.0,
            unit="items",
            destination_bin_id="bin-small",
        )
        try:
            res = confirm_material(worker_session, req)
            results.append(res.id)
        except BinOverflowError:
            overflow_errors.append("BinOverflowError")
        finally:
            worker_session.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(capacity_worker, scan1_id),
            executor.submit(capacity_worker, scan2_id),
        ]
        concurrent.futures.wait(futures)

    verify_session = file_db_factory()
    small_bin = verify_session.query(VirtualBin).filter(VirtualBin.id == "bin-small").one()

    # One succeeded, one got overflow error
    assert len(results) == 1
    assert len(overflow_errors) == 1
    assert small_bin.current_inventory == 4.0  # Did not overflow to 8.0
    verify_session.close()


def test_concurrent_idempotency_key_replay(file_db_factory):
    """
    Two concurrent requests with the identical idempotency key for the same scan.
    Both should safely resolve to the exact same material entry without duplicate inventory.
    """
    session = file_db_factory()
    scan_id = str(uuid4())
    shared_key = f"idem-concurrent-{uuid4()}"
    session.add(Scan(id=scan_id, predicted_category="plastic", confidence=0.9, review_status="pending"))
    session.commit()
    session.close()

    resolved_entry_ids = []

    def replay_worker():
        worker_session = file_db_factory()
        req = MaterialConfirmRequest(
            scan_id=scan_id,
            confirmed_category="plastic",
            quantity=1.0,
            idempotency_key=shared_key,
        )
        try:
            res = confirm_material(worker_session, req)
            resolved_entry_ids.append(res.id)
        finally:
            worker_session.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(replay_worker) for _ in range(2)]
        concurrent.futures.wait(futures)

    assert len(resolved_entry_ids) == 2
    assert resolved_entry_ids[0] == resolved_entry_ids[1]

    verify_session = file_db_factory()
    plastic_bin = verify_session.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").one()
    assert plastic_bin.current_inventory == 1.0  # Not double-counted
    verify_session.close()


# ------------------------------------------------------------------------------
# 2. EVENT REPLAY FOR RECONNECTS (last_event_id / since_id)
# ------------------------------------------------------------------------------

def test_event_replay_since_last_event_id(file_db_factory):
    """
    Verifies that passing last_event_id returns only events committed after that event in chronological order.
    """
    session = file_db_factory()
    events = []
    base_time = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        evt = MaterialEvent(
            id=f"evt-{i:02d}",
            event_type="confirmed",
            affected_category="plastic",
            quantity=1.0,
            timestamp=base_time + timedelta(minutes=i),
        )
        session.add(evt)
        events.append(evt)
    session.commit()

    # Replay after evt-01 -> should return evt-02, evt-03, evt-04
    replayed, cursor, total = get_filtered_events(
        db=session,
        last_event_id="evt-01",
    )
    assert len(replayed) == 3
    assert [e.id for e in replayed] == ["evt-02", "evt-03", "evt-04"]

    # Replay after the latest event evt-04 -> should return empty
    replayed_empty, _, _ = get_filtered_events(db=session, last_event_id="evt-04")
    assert len(replayed_empty) == 0

    session.close()


# ------------------------------------------------------------------------------
# 3. SNAPSHOT HISTORY & PROJECTIONS
# ------------------------------------------------------------------------------

def test_snapshot_record_written_and_queried(file_db_factory):
    """
    Verifies that SnapshotRecord is written during material confirmation and retrievable via get_snapshot_history.
    """
    session = file_db_factory()
    scan_id = str(uuid4())
    session.add(Scan(id=scan_id, predicted_category="plastic", confidence=0.9, review_status="pending"))
    session.commit()

    req = MaterialConfirmRequest(scan_id=scan_id, confirmed_category="plastic", quantity=2.0)
    confirm_material(session, req)

    history = get_snapshot_history(session, limit=10)
    assert len(history) >= 1
    latest = history[0]
    assert latest.total_items == 2.0
    assert "bin-plastic" in latest.bin_states
    assert latest.bin_states["bin-plastic"]["current_inventory"] == 2.0
    session.close()


def test_fill_rates_empty_history_returns_insufficient_data(file_db_factory):
    """
    When no recent material events exist in the observation window, calculate_fill_rates
    must return status='insufficient_data' with estimated_hours_to_full=None.
    """
    session = file_db_factory()
    estimates = calculate_fill_rates_and_time_to_full(session, window_hours=24)
    assert estimates["projection_type"] == "linear_historical_window"
    plastic_est = estimates["bin_estimates"]["bin-plastic"]
    assert plastic_est["status"] == "insufficient_data"
    assert plastic_est["estimated_hours_to_full"] is None
    assert plastic_est["fill_rate_per_hour"] == 0.0
    session.close()


# ------------------------------------------------------------------------------
# 4. EVENT FILTERS & EDGE CASES
# ------------------------------------------------------------------------------

def test_event_filtering_by_category_bin_and_date_range(file_db_factory):
    """
    Verifies that get_filtered_events correctly applies all filter combinations.
    """
    session = file_db_factory()
    t1 = datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 15, 11, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    session.add(MaterialEvent(id="e1", event_type="confirmed", affected_category="plastic", destination_bin_id="bin-plastic", quantity=1.0, timestamp=t1))
    session.add(MaterialEvent(id="e2", event_type="reclassified", affected_category="holding", destination_bin_id="bin-holding", quantity=1.0, timestamp=t2))
    session.add(MaterialEvent(id="e3", event_type="emptied", affected_category="plastic", source_bin_id="bin-plastic", quantity=1.0, timestamp=t3))
    session.commit()

    # Filter by category
    plastic_events, _, count = get_filtered_events(session, category="plastic")
    assert count == 2
    assert {e.id for e in plastic_events} == {"e1", "e3"}

    # Filter by bin ID
    holding_events, _, count = get_filtered_events(session, bin_id="bin-holding")
    assert count == 1
    assert holding_events[0].id == "e2"

    # Filter by date range
    mid_events, _, count = get_filtered_events(session, start_time=t1 + timedelta(minutes=30), end_time=t2 + timedelta(minutes=30))
    assert count == 1
    assert mid_events[0].id == "e2"

    session.close()


def test_transaction_rollback_prevents_websocket_publish(file_db_factory):
    """
    Verifies that if an error occurs inside a transaction, the event listener is NOT published to.
    """
    clear_event_listeners()
    broadcasts = []
    register_event_listener(lambda et, pl: broadcasts.append((et, pl)))

    session = file_db_factory()
    # Attempting to confirm non-existent scan ID
    req = MaterialConfirmRequest(scan_id="non-existent-scan", confirmed_category="plastic", quantity=1.0)
    with pytest.raises(Exception):
        confirm_material(session, req)

    assert len(broadcasts) == 0
    clear_event_listeners()
    session.close()


# ------------------------------------------------------------------------------
# 5. REQUEST ID & ERROR SANITIZATION
# ------------------------------------------------------------------------------

def test_request_id_and_message_sanitization():
    """
    Verifies that get_request_id generates unique IDs and sanitize_message strips secrets and paths.
    """
    req_id = get_request_id()
    assert req_id and len(req_id) >= 16

    dirty_log = "Error accessing file /Users/admin/secrets/api_key.txt with token: secret_abc12345678"
    clean_log = sanitize_message(dirty_log)
    assert "/Users/admin" not in clean_log
    assert "[FILE_PATH]" in clean_log
    assert "secret_abc12345678" not in clean_log
    assert "[REDACTED]" in clean_log
