"""
Pytest configuration and fixtures.
Uses an isolated in-memory SQLite database with foreign keys and WAL mode.
"""
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.database import Base, get_db, init_db
from backend.app.models import Scan, VirtualBin, MaterialEntry, MaterialEvent
from backend.app.routers import materials, twin, events, bins, recommendations
from backend.app.adapters.event_publisher import clear_event_listeners, register_event_listener


@pytest.fixture(scope="function")
def test_db():
    """Isolated SQLite database fixture."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    init_db(target_engine=engine)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def test_app(test_db):
    """FastAPI test application fixture with test database override."""
    app = FastAPI(title="Smart Recycling Agent - Test")

    def override_get_db():
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    app.include_router(materials.router)
    app.include_router(twin.router)
    app.include_router(events.router)
    app.include_router(bins.router)
    app.include_router(recommendations.router)

    return app


@pytest.fixture(scope="function")
def client(test_app):
    return TestClient(test_app)


@pytest.fixture(scope="function")
def sample_scan(test_db):
    scan = Scan(
        id="scan-test-1",
        image_url="http://example.com/item1.jpg",
        predicted_category="plastic",
        confidence=0.92,
        model_identifier="test-model",
        review_status="pending",
    )
    test_db.add(scan)
    test_db.commit()
    test_db.refresh(scan)
    return scan


@pytest.fixture(scope="function")
def ambiguous_scan(test_db):
    scan = Scan(
        id="scan-ambiguous-1",
        image_url="http://example.com/cup.jpg",
        predicted_category="paper",
        confidence=0.55,
        model_identifier="test-model",
        review_status="needs_review",
        top_k_predictions=[
            {"category": "paper", "score": 0.55},
            {"category": "plastic", "score": 0.45},
        ],
        margin=0.10,
    )
    test_db.add(scan)
    test_db.commit()
    test_db.refresh(scan)
    return scan
