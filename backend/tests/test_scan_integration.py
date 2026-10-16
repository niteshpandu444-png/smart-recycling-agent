from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker
from starlette.websockets import WebSocketDisconnect

from backend.app import main
from backend.app.adapters.event_publisher import clear_event_listeners, register_event_listener
from backend.app.database import get_db
from backend.app.models import MaterialEntry, MaterialEvent, Scan, VirtualBin
from backend.app.vision import VisionPrediction, classifier


def jpeg_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (64, 64), color="green").save(stream, format="JPEG")
    return stream.getvalue()


def plastic_prediction() -> VisionPrediction:
    return VisionPrediction(
        predicted_item="Plastic",
        predicted_category="recyclable",
        match_score=0.91,
        manual_review_recommended=False,
        suggested_route="Check local plastic acceptance and preparation rules.",
        explanation="Model class prediction for deterministic integration test.",
        classification_status="success",
        model_class="plastic",
        top_k_predictions=(("plastic", 0.91), ("glass", 0.03)),
        margin=0.88,
    )


@pytest.fixture
def integrated_client(monkeypatch, test_db):
    engine = test_db.get_bind()
    test_sessions = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        session = test_sessions()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "SessionLocal", test_sessions)
    monkeypatch.setattr(classifier, "_session_info", object())
    monkeypatch.setattr(classifier, "_diagnostic_status", "ready")
    monkeypatch.setattr(classifier, "load", lambda: True)
    monkeypatch.setattr(classifier, "predict", lambda _image: plastic_prediction())
    main.app.dependency_overrides[get_db] = override_get_db
    clear_event_listeners()
    try:
        with TestClient(main.app) as client:
            yield client, test_sessions
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        clear_event_listeners()


def test_scan_confirm_snapshot_websocket_and_reopen(integrated_client):
    client, test_sessions = integrated_client
    registered = []
    register_event_listener(lambda event_type, _payload: registered.append(event_type))
    routes = [route.path for route in main.app.routes]
    for prefix in (
        "/api/materials",
        "/api/twin",
        "/api/events",
        "/api/recommendations",
        "/api/bins",
        "/api/analytics",
    ):
        assert sum(path == prefix or path.startswith(prefix + "/") for path in routes) > 0
    assert "/api/materials/api/materials/confirm" not in routes
    assert routes.count("/api/twin/snapshot") == 1

    with client.websocket_connect("/ws") as websocket:
        initial = websocket.receive_json()
        assert initial["type"] == "snapshot"
        assert initial["data"]["total_confirmed_items"] == 0

        response = client.post(
            "/api/scans",
            files={"file": ("waste.jpg", jpeg_bytes(), "image/jpeg")},
        )
        assert response.status_code == 200
        result = response.json()
        assert result["classification_status"] == "success"
        assert result["predicted_category"] == "recyclable"

        with test_sessions() as db:
            scan = db.query(Scan).filter(Scan.id == result["scan_id"]).one()
            assert scan.predicted_category == "plastic"
            assert scan.confidence == result["match_score"]
            assert scan.model_identifier == result["model_identifier"]
            assert scan.review_status == "pending"
            assert scan.top_k_predictions[0] == {"category": "plastic", "score": 0.91}
            assert db.query(VirtualBin).filter_by(id="bin-plastic").one().current_inventory == 0
            assert db.query(MaterialEntry).count() == 0

        confirmation = client.post(
            "/api/materials/confirm",
            json={"scan_id": result["scan_id"], "confirmed_category": "paper"},
        )
        assert confirmation.status_code == 201, confirmation.text
        entry = confirmation.json()
        assert entry["scan_id"] == result["scan_id"]
        assert entry["category"] == "paper"  # User correction is preserved.
        assert entry["predicted_category"] == "plastic"

        live_event = websocket.receive_json()
        assert live_event["type"] == "material_confirmed"
        assert live_event["data"]["scan_id"] == result["scan_id"]

        duplicate = client.post(
            "/api/materials/confirm",
            json={"scan_id": result["scan_id"], "confirmed_category": "paper"},
        )
        assert duplicate.status_code == 409

        snapshot = client.get("/api/twin/snapshot")
        assert snapshot.status_code == 200
        snapshot_body = snapshot.json()
        paper_bin = next(item for item in snapshot_body["bins"] if item["id"] == "bin-paper")
        plastic_bin = next(item for item in snapshot_body["bins"] if item["id"] == "bin-plastic")
        assert paper_bin["current_inventory"] == 1
        assert plastic_bin["current_inventory"] == 0
        assert snapshot_body["total_confirmed_items"] == 1
        assert client.get("/api/events?event_type=confirmed").json()["total_count"] == 1

        assert client.get("/api/twin/snapshot").status_code == 200
        with client.websocket_connect("/ws") as reconnected:
            refreshed = reconnected.receive_json()
            assert refreshed["type"] == "snapshot"
            assert refreshed["data"]["total_confirmed_items"] == 1

    with test_sessions() as reopened_db:
        reopened_scan = reopened_db.query(Scan).filter(Scan.id == result["scan_id"]).one()
        reopened_entry = reopened_db.query(MaterialEntry).filter(MaterialEntry.scan_id == result["scan_id"]).one()
        assert reopened_scan.review_status == "confirmed"
        assert reopened_entry.confirmed_category == "paper"
        assert reopened_db.query(MaterialEvent).filter(MaterialEvent.scan_id == result["scan_id"]).count() == 1
        assert reopened_db.query(VirtualBin).filter_by(id="bin-paper").one().current_inventory == 1
    assert registered == ["material_confirmed"]


def test_websocket_allows_configured_origin_and_rejects_unlisted_origin(integrated_client):
    client, _test_sessions = integrated_client
    with client.websocket_connect("/ws", headers={"origin": main.CORS_ORIGINS[0]}) as websocket:
        assert websocket.receive_json()["type"] == "snapshot"

    with pytest.raises(WebSocketDisconnect) as disconnected:
        with client.websocket_connect("/ws", headers={"origin": "https://untrusted.example"}):
            pass
    assert disconnected.value.code == 1008


def test_uncertain_scan_persists_as_reviewable_and_can_be_corrected(integrated_client, monkeypatch):
    client, test_sessions = integrated_client
    uncertain = VisionPrediction(
        predicted_item=None,
        predicted_category=None,
        match_score=0.51,
        manual_review_recommended=True,
        suggested_route="Manual review requested.",
        explanation="Model uncertainty heuristic.",
        classification_status="uncertain",
        model_class="trash",
        top_k_predictions=(("trash", 0.51), ("plastic", 0.30)),
        margin=0.21,
    )
    monkeypatch.setattr(classifier, "predict", lambda _image: uncertain)
    response = client.post("/api/scans", files={"file": ("uncertain.jpg", jpeg_bytes(), "image/jpeg")})
    assert response.status_code == 200
    body = response.json()
    assert body["predicted_category"] is None
    with test_sessions() as db:
        scan = db.query(Scan).filter(Scan.id == body["scan_id"]).one()
        assert scan.predicted_category == "holding"
        assert scan.review_status == "needs_review"
        assert db.query(VirtualBin).filter_by(id="bin-holding").one().current_inventory == 0

    confirmation = client.post(
        "/api/materials/confirm",
        json={
            "scan_id": body["scan_id"],
            "confirmed_category": "plastic",
            "confirmation_source": "manual_override",
        },
    )
    assert confirmation.status_code == 201, confirmation.text
    assert confirmation.json()["confirmed_category"] == "plastic"


def test_scan_database_failure_does_not_return_success(integrated_client):
    client, _ = integrated_client

    class BrokenSession:
        def add(self, _record):
            pass

        def commit(self):
            raise RuntimeError("simulated database failure")

        def rollback(self):
            pass

    def broken_db():
        yield BrokenSession()

    main.app.dependency_overrides[get_db] = broken_db
    response = client.post("/api/scans", files={"file": ("waste.jpg", jpeg_bytes(), "image/jpeg")})
    assert response.status_code == 503
    assert response.json()["detail"] == "Scan result could not be stored."


@pytest.mark.parametrize(
    ("confirmed_category", "destination"),
    [
        ("hazardous", "bin-holding"),
        ("reusable", "bin-holding"),
        ("biodegradable", "bin-organic"),
    ],
)
def test_vision_category_aliases_use_supported_twin_destinations(
    client, test_db, sample_scan, confirmed_category, destination
):
    response = client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": confirmed_category},
    )
    assert response.status_code == 201, response.text
    assert response.json()["confirmed_category"] == confirmed_category
    entry = test_db.query(MaterialEntry).filter_by(scan_id=sample_scan.id).one()
    assert entry.destination == destination
    assert test_db.query(VirtualBin).filter_by(id=destination).one().current_inventory == 1
