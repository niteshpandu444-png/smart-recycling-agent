"""Focused SQLite concurrency regressions for inventory confirmation."""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import init_db
from backend.app.models import MaterialEntry, MaterialEvent, Scan, VirtualBin
from backend.app.adapters.schemas import MaterialConfirmRequest
from backend.app.services.material_service import BinOverflowError, confirm_material


def _sessions(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'confirm-concurrency.db'}",
        connect_args={"check_same_thread": False, "timeout": 30.0},
    )
    init_db(target_engine=engine)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_concurrent_same_scan_idempotency_replay_commits_once(tmp_path):
    engine, sessions = _sessions(tmp_path)
    scan_id = str(uuid4())
    replay_key = f"concurrent-{uuid4()}"
    with sessions() as db:
        db.add(Scan(
            id=scan_id,
            predicted_category="plastic",
            confidence=0.9,
            model_identifier="test-model",
            review_status="pending",
        ))
        db.commit()

    def confirm_once():
        with sessions() as db:
            entry = confirm_material(db, MaterialConfirmRequest(
                scan_id=scan_id,
                confirmed_category="plastic",
                idempotency_key=replay_key,
            ))
            return entry.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        entry_ids = list(pool.map(lambda _: confirm_once(), range(2)))

    with sessions() as db:
        assert entry_ids[0] == entry_ids[1]
        assert db.query(MaterialEntry).filter_by(scan_id=scan_id).count() == 1
        assert db.query(MaterialEvent).filter_by(scan_id=scan_id).count() == 1
        assert db.query(VirtualBin).filter_by(id="bin-plastic").one().current_inventory == 1.0
    engine.dispose()


def test_concurrent_confirmations_cannot_overfill_bin(tmp_path):
    engine, sessions = _sessions(tmp_path)
    with sessions() as db:
        small_bin = db.query(VirtualBin).filter_by(id="bin-glass").one()
        small_bin.capacity = 5.0
        scan_ids = [str(uuid4()), str(uuid4())]
        db.add_all([
            Scan(
                id=scan_id,
                predicted_category="glass",
                confidence=0.9,
                model_identifier="test-model",
                review_status="pending",
            )
            for scan_id in scan_ids
        ])
        db.commit()

    def confirm(scan_id):
        with sessions() as db:
            try:
                confirm_material(db, MaterialConfirmRequest(
                    scan_id=scan_id,
                    confirmed_category="glass",
                    quantity=4.0,
                    destination_bin_id="bin-glass",
                ))
                return "confirmed"
            except BinOverflowError:
                return "overflow"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(confirm, scan_ids))

    with sessions() as db:
        assert sorted(outcomes) == ["confirmed", "overflow"]
        glass_bin = db.query(VirtualBin).filter_by(id="bin-glass").one()
        assert glass_bin.current_inventory == 4.0
        assert db.query(MaterialEntry).count() == 1
        assert db.query(MaterialEvent).count() == 1
    engine.dispose()