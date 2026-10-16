"""Mixed-waste batch scanning: detector decode, review rules, and API behaviour.

The suite is split so that the parts that cannot depend on a downloaded model
artifact are exercised unconditionally:

* detector geometry, NMS, same-object collapsing, and output decoding run against
  a stub ONNX session, so they are deterministic and need no model file;
* review-decision rules run against synthetic detections;
* the batch API runs against the in-memory test database with the detector
  stubbed;
* one optional integration test exercises the real artifact when it is present
  locally and is skipped otherwise.
"""
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import sessionmaker

from backend.app import main
from backend.app.adapters.event_publisher import clear_event_listeners
from backend.app.database import get_db
from backend.app.models import BatchScan, MaterialEntry, MaterialEvent, Scan, VirtualBin
from backend.app.services.batch_scan_service import (
    REVIEW_REASON_AMBIGUOUS_MATERIAL,
    REVIEW_REASON_CROSS_CHECK,
    REVIEW_REASON_FEATURELESS_CROP,
    REVIEW_REASON_LOW_SCORE,
    REVIEW_REASON_OVERLAPPING_MATERIAL,
    REVIEW_REASON_UNSUPPORTED_CLASS,
    CrossCheckResult,
    analyze_detections,
    make_classifier_cross_check,
)
from backend.app.vision import PERSISTED_CATEGORY_BY_MODEL_CLASS, VisionPrediction
from backend.app.vision_detector import (
    DETECTOR_CLASS_NAMES,
    Detection,
    WasteDetector,
    _SessionInfo,
    _collapse_same_object_duplicates,
    _compute_letterbox,
    _non_maximum_suppression,
)


def textured_image(size=(1000, 500), seed=0) -> Image.Image:
    """A non-uniform image.

    Crop-texture analysis flags featureless regions for review, so tests about
    other rules must feed it an image that actually has texture.
    """
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))


def jpeg_bytes(size=(640, 480)) -> bytes:
    stream = BytesIO()
    textured_image(size).save(stream, format="JPEG")
    return stream.getvalue()


# ---------------------------------------------------------------------------
# Detector geometry and decoding (no model artifact required)
# ---------------------------------------------------------------------------


def test_letterbox_preserves_aspect_ratio_and_reports_padding():
    canvas, gain, offset_x, offset_y = _compute_letterbox(Image.new("RGB", (320, 160)))

    assert canvas.size == (640, 640)
    assert gain == 2.0
    assert offset_x == 0
    assert offset_y == 160
    # Padding rows must be the documented neutral grey, not black.
    assert canvas.getpixel((5, 5)) == (114, 114, 114)
    assert canvas.getpixel((5, 200)) != (114, 114, 114)


def test_non_maximum_suppression_keeps_best_of_overlapping_boxes():
    boxes = np.array(
        [[0.0, 0.0, 100.0, 100.0], [2.0, 2.0, 101.0, 101.0], [300.0, 0.0, 400.0, 100.0]],
        dtype=np.float32,
    )
    scores = np.array([0.9, 0.8, 0.7], dtype=np.float32)

    keep = _non_maximum_suppression(boxes, scores, iou_threshold=0.45)

    assert keep == [0, 2]


def test_same_object_duplicates_collapse_and_keep_the_losing_label():
    # One jar, returned twice with two labels at nearly identical boxes.
    detections = [
        Detection("metal", 0.60, (10.0, 10.0, 200.0, 300.0)),
        Detection("glass", 0.54, (11.0, 10.0, 201.0, 301.0)),
        Detection("paper", 0.44, (400.0, 10.0, 600.0, 300.0)),
    ]

    kept = _collapse_same_object_duplicates(detections)

    assert len(kept) == 2
    assert kept[0].class_name == "metal"
    assert kept[0].alternate_labels == (("glass", 0.54),)
    # The losing label still counts towards the ambiguity margin.
    assert kept[0].runner_up == ("glass", 0.54)
    assert kept[0].margin == pytest.approx(0.06)
    assert kept[1].class_name == "paper"


class _StubInput:
    name = "images"
    type = "tensor(float)"
    shape = [1, 3, 640, 640]


class _StubOutput:
    name = "output0"
    type = "tensor(float)"
    shape = [1, 4 + len(DETECTOR_CLASS_NAMES), 8400]


class _StubSession:
    """Minimal ONNX Runtime session stand-in."""

    def __init__(self, output=None, inputs=None, outputs=None):
        self._output = output
        self._inputs = inputs if inputs is not None else [_StubInput()]
        self._outputs = outputs if outputs is not None else [_StubOutput()]

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def get_inputs(self):
        return self._inputs

    def get_outputs(self):
        return self._outputs

    def run(self, _names, _feed):
        return [self._output]


def _detector_returning(output) -> WasteDetector:
    detector = WasteDetector(model_path="unused.onnx")
    detector._session_info = _SessionInfo(_StubSession(output), "images", "output0", (1, 3, 640, 640))
    return detector


def test_session_validation_rejects_a_different_class_count():
    class _WrongClassOutput:
        name = "output0"
        type = "tensor(float)"
        shape = [1, 4 + len(DETECTOR_CLASS_NAMES) + 1, 8400]

    ort = type("Ort", (), {"InferenceSession": lambda *a, **k: _StubSession(outputs=[_WrongClassOutput()])})()

    with pytest.raises(Exception, match="class count"):
        WasteDetector()._create_session("ignored.onnx", ort)


def test_detector_maps_boxes_back_out_of_letterbox_space():
    # 320x160 source becomes 640x320 with a 160px top pad (gain 2).
    # Anchor (cx=60, cy=220, w=100, h=100) => letterbox box (10,170)-(110,270)
    # => original pixels (5,5)-(55,55).
    raw = np.zeros((1, 4 + len(DETECTOR_CLASS_NAMES), 8400), dtype=np.float32)
    raw[0, 0, 0] = 60.0
    raw[0, 1, 0] = 220.0
    raw[0, 2, 0] = 100.0
    raw[0, 3, 0] = 100.0
    raw[0, 4 + DETECTOR_CLASS_NAMES.index("plastic"), 0] = 0.88

    detections = _detector_returning(raw).detect(Image.new("RGB", (320, 160)))

    assert len(detections) == 1
    detection = detections[0]
    assert detection.class_name == "plastic"
    assert detection.score == pytest.approx(0.88, abs=1e-5)
    assert detection.box == pytest.approx((5.0, 5.0, 55.0, 55.0), abs=0.51)


def test_detector_returns_empty_list_for_a_blank_scene():
    raw = np.full((1, 4 + len(DETECTOR_CLASS_NAMES), 8400), 0.01, dtype=np.float32)

    assert _detector_returning(raw).detect(Image.new("RGB", (640, 640))) == []


# ---------------------------------------------------------------------------
# Review-decision rules (synthetic detections, no model required)
# ---------------------------------------------------------------------------


def _analyze(detections, image=None, cross_check=None):
    return analyze_detections(
        image if image is not None else textured_image((1000, 500)),
        detections,
        detector_identifier="test-detector",
        cross_check=cross_check,
    )


def test_high_confidence_supported_detection_is_ready():
    (item,) = _analyze(
        [Detection("glass", 0.91, (10.0, 10.0, 300.0, 400.0), class_scores=(("glass", 0.91),))],
    )

    assert item.review_status == "ready"
    assert item.review_reasons == ()
    assert item.category == "glass"
    assert item.suggested_destination == "bin-glass"
    assert item.attempts_holding_bin is False


def test_low_score_detection_is_surfaced_but_flagged_for_review():
    (item,) = _analyze(
        [Detection("plastic", 0.30, (10.0, 10.0, 300.0, 400.0), class_scores=(("plastic", 0.30),))],
    )

    assert item.review_status == "needs_review"
    assert REVIEW_REASON_LOW_SCORE in item.review_reasons
    # A weak but real detection is still reported rather than dropped.
    assert item.category == "plastic"
    assert item.suggested_destination == "bin-plastic"


def test_unsupported_material_class_routes_to_holding_and_needs_review():
    (item,) = _analyze(
        [Detection("trash", 0.66, (10.0, 10.0, 300.0, 400.0), class_scores=(("trash", 0.66),))],
    )

    assert item.review_status == "needs_review"
    assert REVIEW_REASON_UNSUPPORTED_CLASS in item.review_reasons
    assert item.category == "holding"
    assert item.suggested_destination == "bin-holding"
    assert item.attempts_holding_bin is True


def test_overlapping_same_object_material_conflict_requests_review():
    (item,) = _analyze(
        [
            Detection(
                "metal",
                0.60,
                (10.0, 10.0, 300.0, 400.0),
                class_scores=(("metal", 0.60),),
                alternate_labels=(("glass", 0.55),),
            )
        ],
    )

    assert item.review_status == "needs_review"
    assert REVIEW_REASON_OVERLAPPING_MATERIAL in item.review_reasons
    assert item.runner_up == ("glass", 0.55)


def test_confusable_pair_with_narrow_margin_requests_review():
    (item,) = _analyze(
        [
            Detection(
                "plastic",
                0.62,
                (10.0, 10.0, 300.0, 400.0),
                class_scores=(("plastic", 0.62), ("paper", 0.58)),
            )
        ],
    )

    assert item.review_status == "needs_review"
    assert REVIEW_REASON_AMBIGUOUS_MATERIAL in item.review_reasons


def test_cross_check_disagreement_requests_review_and_is_recorded():
    def disagreeing(_crop):
        return CrossCheckResult(
            model_class="paper", category="paper", score=0.80, model_identifier="stub-classifier"
        )

    (item,) = _analyze(
        [Detection("plastic", 0.90, (10.0, 10.0, 300.0, 400.0), class_scores=(("plastic", 0.90),))],
        cross_check=disagreeing,
    )

    assert item.review_status == "needs_review"
    assert REVIEW_REASON_CROSS_CHECK in item.review_reasons
    assert item.cross_check is not None
    assert item.cross_check.category == "paper"
    assert item.metadata["cross_check"] == "completed"


def test_cross_check_agreement_keeps_item_ready():
    def agreeing(_crop):
        return CrossCheckResult(
            model_class="plastic", category="plastic", score=0.77, model_identifier="stub-classifier"
        )

    (item,) = _analyze(
        [Detection("plastic", 0.90, (10.0, 10.0, 300.0, 400.0), class_scores=(("plastic", 0.90),))],
        cross_check=agreeing,
    )

    assert item.review_status == "ready"
    assert item.cross_check is not None


def test_cross_check_is_skipped_for_a_crop_that_is_too_small():
    (item,) = _analyze(
        [Detection("plastic", 0.90, (10.0, 10.0, 30.0, 30.0), class_scores=(("plastic", 0.90),))],
        cross_check=lambda _crop: pytest.fail("cross-check must not run on a tiny crop"),
    )

    assert item.metadata["cross_check"] == "skipped_crop_too_small"
    assert item.cross_check is None


def test_cross_check_failure_does_not_fail_the_item():
    def exploding(_crop):
        raise RuntimeError("inference exploded")

    (item,) = _analyze(
        [Detection("plastic", 0.90, (10.0, 10.0, 300.0, 400.0), class_scores=(("plastic", 0.90),))],
        cross_check=exploding,
    )

    assert item.metadata["cross_check"] == "error"
    assert item.review_status == "ready"


def test_item_ids_are_stable_and_boxes_are_normalized():
    items = _analyze(
        [
            Detection("glass", 0.90, (100.0, 50.0, 300.0, 250.0), class_scores=(("glass", 0.90),)),
            Detection("paper", 0.80, (500.0, 100.0, 900.0, 400.0), class_scores=(("paper", 0.80),)),
        ],
        image=Image.new("RGB", (1000, 500)),
    )

    assert [item.item_id for item in items] == ["item-01", "item-02"]
    assert items[0].box_normalized == (0.1, 0.1, 0.3, 0.5)
    assert items[1].box_normalized == (0.5, 0.2, 0.9, 0.8)


def test_no_detections_produces_no_items():
    assert _analyze([]) == []


def test_featureless_crop_is_flagged_even_when_the_detector_is_confident():
    # Measured on the real artifact: a uniformly coloured region produced a
    # confident ``glass`` label. No score threshold catches that, so the region's
    # own lack of texture is the signal that sends it to review.
    (item,) = _analyze(
        [Detection("glass", 0.83, (10.0, 10.0, 300.0, 400.0), class_scores=(("glass", 0.83),))],
        image=Image.new("RGB", (1000, 500), (60, 170, 80)),
    )

    assert item.review_status == "needs_review"
    assert REVIEW_REASON_FEATURELESS_CROP in item.review_reasons
    assert item.metadata["crop_grayscale_stddev"] == 0.0


def test_textured_crop_is_not_flagged_as_featureless():
    (item,) = _analyze(
        [Detection("glass", 0.83, (10.0, 10.0, 300.0, 400.0), class_scores=(("glass", 0.83),))]
    )

    assert item.review_status == "ready"
    assert item.metadata["crop_grayscale_stddev"] > 8.0


def test_classifier_cross_check_uses_only_public_classifier_attributes():
    class _StubClassifier:
        ready = True
        model_identifier = "stub-model"

        def predict(self, _crop):
            return VisionPrediction(
                predicted_item="Plastic",
                predicted_category="recyclable",
                match_score=0.66,
                manual_review_recommended=False,
                suggested_route="route",
                explanation="explanation",
                classification_status="success",
                model_class="plastic",
            )

    result = make_classifier_cross_check(_StubClassifier())(Image.new("RGB", (80, 80)))

    assert result is not None
    assert result.category == PERSISTED_CATEGORY_BY_MODEL_CLASS["plastic"]
    assert result.score == pytest.approx(0.66)


def test_classifier_cross_check_returns_none_when_the_classifier_is_unavailable():
    class _NotReady:
        ready = False

        def predict(self, _crop):
            raise AssertionError("must not be called")

    assert make_classifier_cross_check(_NotReady())(Image.new("RGB", (80, 80))) is None


# ---------------------------------------------------------------------------
# API behaviour
# ---------------------------------------------------------------------------


def plastic_and_paper_detections():
    return [
        Detection("plastic", 0.90, (40.0, 40.0, 240.0, 380.0), class_scores=(("plastic", 0.90),)),
        Detection("paper", 0.80, (300.0, 40.0, 560.0, 380.0), class_scores=(("paper", 0.80),)),
    ]


@pytest.fixture
def batch_client(monkeypatch, test_db):
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
    monkeypatch.setattr(main.detector, "_session_info", object())
    monkeypatch.setattr(main.detector, "_diagnostic_status", "ready")
    monkeypatch.setattr(main.detector, "detect", lambda _image: plastic_and_paper_detections())
    monkeypatch.setattr(main.classifier, "_session_info", None)
    monkeypatch.setattr(main.classifier, "_diagnostic_status", "not_initialized")
    # The lifespan starts background model loaders; stub them so the suite never
    # reads a multi-megabyte artifact off disk just to build a test client.
    monkeypatch.setattr(main.detector, "load", lambda: True)
    monkeypatch.setattr(main.classifier, "load", lambda: True)
    main.app.dependency_overrides[get_db] = override_get_db
    clear_event_listeners()
    try:
        with TestClient(main.app) as client:
            yield client, test_sessions
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        clear_event_listeners()


def post_batch(client, source="upload", payload=None):
    return client.post(
        "/api/scans/batch",
        files={"file": ("scene.jpg", payload or jpeg_bytes(), "image/jpeg")},
        data={"source": source},
    )


def test_detector_status_endpoint_reports_provenance(batch_client):
    client, _ = batch_client

    response = client.get("/api/model/detector/status")

    assert response.status_code == 200
    body = response.json()
    assert body["detector_class_names"] == list(DETECTOR_CLASS_NAMES)
    assert body["detector_identifier"] == main.detector.model_identifier
    assert "AGPL-3.0" in body["detector_license"]
    assert body["initialized_successfully"] is True


def test_single_item_status_contract_is_unchanged(batch_client):
    client, _ = batch_client

    response = client.get("/api/model/status")

    assert response.status_code == 200
    assert response.json() == {
        "initialized_successfully": False,
        "model_identifier": main.classifier.model_identifier,
        "inference_available": False,
        "diagnostic_status": "not_initialized",
    }


def test_batch_scan_persists_one_pending_scan_per_item_without_touching_inventory(batch_client):
    client, test_sessions = batch_client

    response = post_batch(client)

    assert response.status_code == 200
    body = response.json()
    assert body["detection_count"] == 2
    assert body["review_required_count"] == 0
    assert [item["item_id"] for item in body["items"]] == ["item-01", "item-02"]
    assert [item["category"] for item in body["items"]] == ["plastic", "paper"]
    assert body["items"][0]["box"]["normalized_x1"] == pytest.approx(40 / 640, abs=1e-6)
    assert body["detector_license"].startswith("AGPL-3.0")

    with test_sessions() as db:
        batch = db.query(BatchScan).filter(BatchScan.id == body["batch_id"]).one()
        assert batch.detection_count == 2
        assert batch.category_totals == {"plastic": 1.0, "paper": 1.0}
        scans = db.query(Scan).filter(Scan.id.in_(batch.item_scan_ids)).all()
        assert len(scans) == 2
        assert {scan.review_status for scan in scans} == {"pending"}
        # Four bins exist in the seeded fixture, but no inventory may move yet.
        assert db.query(MaterialEntry).count() == 0
        assert sum(bin.current_inventory for bin in db.query(VirtualBin).all()) == 0


def test_batch_scan_returns_an_empty_result_for_a_scene_without_objects(batch_client, monkeypatch):
    client, test_sessions = batch_client
    monkeypatch.setattr(main.detector, "detect", lambda _image: [])

    response = post_batch(client)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["detection_count"] == 0
    assert any("No objects were detected" in note for note in body["notes"])
    with test_sessions() as db:
        assert db.query(Scan).count() == 0
        assert db.query(BatchScan).filter(BatchScan.id == body["batch_id"]).one().detection_count == 0


def test_batch_scan_marks_needs_review_items(batch_client, monkeypatch):
    client, test_sessions = batch_client
    monkeypatch.setattr(
        main.detector,
        "detect",
        lambda _image: [Detection("trash", 0.70, (10.0, 10.0, 300.0, 300.0), class_scores=(("trash", 0.70),))],
    )

    response = post_batch(client, source="camera")
    body = response.json()

    assert response.status_code == 200
    assert body["review_required_count"] == 1
    item = body["items"][0]
    assert item["review_status"] == "needs_review"
    assert item["attempts_holding_bin"] is True
    assert item["suggested_destination"] == "bin-holding"
    with test_sessions() as db:
        scan = db.query(Scan).filter(Scan.id == item["scan_id"]).one()
        assert scan.review_status == "needs_review"
        assert db.query(BatchScan).filter(BatchScan.id == body["batch_id"]).one().source == "camera"


def test_batch_scan_rejects_an_unsupported_source(batch_client):
    client, _ = batch_client

    assert post_batch(client, source="satellite").status_code == 422


def test_batch_scan_rejects_malformed_and_unsupported_images(batch_client):
    client, _ = batch_client

    assert post_batch(client, payload=b"not an image").status_code == 422

    stream = BytesIO()
    Image.new("RGB", (64, 64), color="blue").save(stream, format="GIF")
    assert post_batch(client, payload=stream.getvalue()).status_code == 415


def test_batch_scan_returns_503_when_the_detector_is_unavailable(batch_client, monkeypatch):
    client, test_sessions = batch_client
    monkeypatch.setattr(main.detector, "_session_info", None)

    response = post_batch(client)

    assert response.status_code == 503
    with test_sessions() as db:
        assert db.query(BatchScan).count() == 0
        assert db.query(Scan).count() == 0


def test_batch_scan_returns_503_without_persisting_when_inference_fails(batch_client, monkeypatch):
    client, test_sessions = batch_client

    def exploding(_image):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(main.detector, "detect", exploding)

    assert post_batch(client).status_code == 503
    with test_sessions() as db:
        assert db.query(BatchScan).count() == 0
        assert db.query(Scan).count() == 0


def confirm_batch(client, items):
    return client.post("/api/materials/confirm-batch", json={"items": items})


def batch_confirm_payload(scan_id, category, **overrides):
    payload = {
        "scan_id": scan_id,
        "confirmed_category": category,
        "confirmation_source": "user_corrected",
    }
    payload.update(overrides)
    return payload


def test_batch_confirmation_records_every_accepted_item(batch_client):
    client, test_sessions = batch_client
    body = post_batch(client).json()
    scan_ids = [item["scan_id"] for item in body["items"]]

    response = confirm_batch(
        client,
        [
            batch_confirm_payload(scan_ids[0], "plastic", idempotency_key="key-1"),
            batch_confirm_payload(scan_ids[1], "paper", idempotency_key="key-2"),
        ],
    )

    assert response.status_code == 200
    result = response.json()
    assert result["confirmed_count"] == 2
    assert result["failed_count"] == 0
    assert {item["status"] for item in result["results"]} == {"confirmed"}
    assert {item["destination"] for item in result["results"]} == {"bin-plastic", "bin-paper"}

    with test_sessions() as db:
        assert db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").one().current_inventory == 1
        assert db.query(VirtualBin).filter(VirtualBin.id == "bin-paper").one().current_inventory == 1
        assert db.query(MaterialEntry).count() == 2
        assert db.query(MaterialEvent).filter(MaterialEvent.event_type == "confirmed").count() == 2


def test_batch_confirmation_replay_does_not_double_count(batch_client):
    client, test_sessions = batch_client
    body = post_batch(client).json()
    scan_id = body["items"][0]["scan_id"]
    payload = [batch_confirm_payload(scan_id, "plastic", idempotency_key="replay-key")]

    assert confirm_batch(client, payload).json()["confirmed_count"] == 1
    second = confirm_batch(client, payload).json()

    assert second["confirmed_count"] + second["already_confirmed_count"] == 1
    with test_sessions() as db:
        assert db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").one().current_inventory == 1
        assert db.query(MaterialEntry).count() == 1
        assert db.query(MaterialEvent).filter(MaterialEvent.event_type == "confirmed").count() == 1


def test_batch_confirmation_reports_a_partial_outcome_honestly(batch_client):
    client, test_sessions = batch_client
    body = post_batch(client).json()
    scan_ids = [item["scan_id"] for item in body["items"]]
    # Already confirmed once, so this scan must not be accepted a second time.
    assert confirm_batch(client, [batch_confirm_payload(scan_ids[0], "plastic")]).json()["confirmed_count"] == 1

    response = confirm_batch(
        client,
        [
            batch_confirm_payload(scan_ids[0], "plastic"),
            batch_confirm_payload(scan_ids[1], "paper"),
        ],
    )

    assert response.status_code == 200
    result = response.json()
    assert result["confirmed_count"] == 1
    assert result["already_confirmed_count"] == 1
    assert result["failed_count"] == 0
    statuses = {item["scan_id"]: item["status"] for item in result["results"]}
    assert statuses[scan_ids[0]] == "already_confirmed"
    assert statuses[scan_ids[1]] == "confirmed"
    with test_sessions() as db:
        assert db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").one().current_inventory == 1


def test_batch_confirmation_reports_per_item_failures_without_losing_the_rest(batch_client):
    client, test_sessions = batch_client
    body = post_batch(client).json()
    scan_ids = [item["scan_id"] for item in body["items"]]

    response = confirm_batch(
        client,
        [
            batch_confirm_payload("does-not-exist", "plastic"),
            batch_confirm_payload(scan_ids[0], "not-a-category"),
            batch_confirm_payload(scan_ids[1], "paper"),
        ],
    )

    assert response.status_code == 200
    result = response.json()
    assert result["confirmed_count"] == 1
    assert result["failed_count"] == 2
    errors = [item["error"] for item in result["results"] if item["status"] == "failed"]
    assert any("was not found" in error for error in errors)
    assert any("Invalid category" in error for error in errors)
    # The one valid item still committed.
    with test_sessions() as db:
        assert db.query(VirtualBin).filter(VirtualBin.id == "bin-paper").one().current_inventory == 1


def test_batch_confirmation_rejects_an_empty_item_list(batch_client):
    client, _ = batch_client

    assert confirm_batch(client, []).status_code == 422


# ---------------------------------------------------------------------------
# Digital Twin batch reporting
# ---------------------------------------------------------------------------


def test_twin_snapshot_reports_batch_activity_separately_from_inventory(batch_client):
    client, _ = batch_client
    body = post_batch(client).json()
    scan_ids = [item["scan_id"] for item in body["items"]]
    confirm_batch(client, [batch_confirm_payload(scan_ids[0], "plastic")])

    snapshot = client.get("/api/twin/snapshot").json()

    assert snapshot["batch_scan_count"] == 1
    assert snapshot["detected_item_totals"] == {"paper": 1.0, "plastic": 1.0}
    # One detected item is still unconfirmed, so confirmed stays at one.
    assert snapshot["total_confirmed_items"] == 1
    assert snapshot["confirmed_from_batch_count"] == 1
    activity = snapshot["recent_batch_activity"]
    assert len(activity) == 1
    assert activity[0]["batch_id"] == body["batch_id"]
    assert activity[0]["detection_count"] == 2
    assert activity[0]["confirmed_count"] == 1
    assert activity[0]["pending_review_count"] == 0


def test_twin_snapshot_counts_items_awaiting_review(batch_client, monkeypatch):
    client, _ = batch_client
    monkeypatch.setattr(
        main.detector,
        "detect",
        lambda _image: [Detection("trash", 0.70, (10.0, 10.0, 300.0, 300.0), class_scores=(("trash", 0.70),))],
    )
    post_batch(client)

    snapshot = client.get("/api/twin/snapshot").json()

    assert snapshot["needs_review_scan_count"] == 1
    assert snapshot["total_confirmed_items"] == 0


# ---------------------------------------------------------------------------
# Optional integration test against the real artifact
# ---------------------------------------------------------------------------


def real_detector_or_skip() -> WasteDetector:
    detector = WasteDetector()
    if not detector.model_path.is_file():
        pytest.skip("real detector artifact is not present locally")
    if not detector.load():
        pytest.skip(f"real detector artifact could not be loaded ({detector.diagnostic_status})")
    return detector


def test_real_detector_does_not_invent_objects_in_empty_scenes():
    detector = real_detector_or_skip()

    # Docstring-pinned guarantee: neutral or dark featureless canvases produce no
    # detections at all. (Saturated flat colours are a separate, documented
    # false-positive mode that the review rules catch instead; see
    # test_featureless_crop_is_flagged_even_when_the_detector_is_confident.)
    for colour in ((235, 235, 235), (120, 120, 120), (0, 0, 0), (20, 20, 20)):
        assert detector.detect(Image.new("RGB", (480, 480), colour)) == []


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "test_images").is_dir(),
    reason="local waste test images are not present",
)
def test_real_detector_finds_multiple_distinct_objects_in_one_scene():
    """The core claim of mixed-waste mode: several real items, several detections.

    The scene is composited from the repository's own local waste photographs
    placed side by side. It is a constructed scene rather than a photograph of a
    real pile, which is stated here so the result is not overstated.
    """
    detector = real_detector_or_skip()
    images_dir = Path(__file__).resolve().parents[1] / "test_images"
    sources = [images_dir / name for name in ("glassjar.jpeg", "cardboard.jpg", "plastic_bottle.jpg")]
    available = [path for path in sources if path.is_file()]
    if len(available) < 2:
        pytest.skip("not enough local waste test images to build a scene")

    tile = 420
    scene = Image.new("RGB", (tile * len(available), tile), (205, 205, 205))
    for index, path in enumerate(available):
        scene.paste(Image.open(path).convert("RGB").resize((tile, tile)), (index * tile, 0))

    detections = detector.detect(scene)

    assert len(detections) >= 2, f"expected several objects, got {detections}"
    assert {detection.class_name for detection in detections} <= set(DETECTOR_CLASS_NAMES)
    for detection in detections:
        x1, y1, x2, y2 = detection.box
        assert 0 <= x1 < x2 <= scene.width
        assert 0 <= y1 < y2 <= scene.height
        assert detection.score >= 0.20

    # Distinct objects, not one box reported twice: no pair may overlap heavily.
    boxes = [detection.box for detection in detections]
    for index, first in enumerate(boxes):
        for second in boxes[index + 1:]:
            overlap_x = max(0.0, min(first[2], second[2]) - max(first[0], second[0]))
            overlap_y = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
            intersection = overlap_x * overlap_y
            union = (
                (first[2] - first[0]) * (first[3] - first[1])
                + (second[2] - second[0]) * (second[3] - second[1])
                - intersection
            )
            assert intersection / union < 0.5
