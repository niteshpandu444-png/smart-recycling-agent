from io import BytesIO
import sys
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from PIL import Image

from backend.app.main import app
from backend.app.schemas import ClassificationResponse
from backend.app.vision import (
    CLASS_NAMES,
    CLASS_POLICIES,
    ModelDownloadError,
    VisionClassifier,
    VisionPrediction,
    _SessionInfo,
    classifier,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def jpeg_bytes() -> bytes:
    stream = BytesIO()
    Image.new("RGB", (64, 64), color="green").save(stream, format="JPEG")
    return stream.getvalue()


def success_prediction() -> VisionPrediction:
    return VisionPrediction(
        predicted_item="Plastic",
        predicted_category="recyclable",
        match_score=0.71,
        manual_review_recommended=False,
        suggested_route="Check local acceptance and preparation rules.",
        explanation="Visual candidate only; score is not calibrated.",
        classification_status="success",
    )


class FakeSession:
    def __init__(self, values):
        self.values = values
        self.feed = None

    def get_providers(self):
        return ["CPUExecutionProvider"]

    def get_inputs(self):
        return [SimpleNamespace(name="images", shape=[1, 3, 224, 224], type="tensor(float)")]

    def get_outputs(self):
        return [SimpleNamespace(name="scores", shape=[1, 8], type="tensor(float)")]

    def run(self, output_names, feed):
        self.feed = (output_names, feed)
        return [self.values]


def model_with_scores(scores) -> tuple[VisionClassifier, FakeSession]:
    model = VisionClassifier("unused.onnx")
    session = FakeSession(np.asarray([scores], dtype=np.float32))
    model._session_info = _SessionInfo(session, "images", "scores", (1, 3, 224, 224))
    return model, session


@pytest.fixture
def vision_ready(monkeypatch):
    monkeypatch.setattr(classifier, "_session_info", _SessionInfo(object(), "x", "y", (1, 3, 224, 224)))
    monkeypatch.setattr(classifier, "_diagnostic_status", "ready")
    monkeypatch.setattr(classifier, "predict", lambda _image: success_prediction())


class FakeOrt:
    def __init__(self, session):
        self.session = session

    def InferenceSession(self, _path, providers):
        assert providers == ["CPUExecutionProvider"]
        return self.session


def test_onnx_initialization_inspects_and_accepts_documented_metadata(tmp_path):
    model = VisionClassifier(tmp_path / "model.onnx")
    session = FakeSession(np.array([[0.01] * 8], dtype=np.float32))
    info = model._create_session(tmp_path / "model.onnx", FakeOrt(session))
    assert info.input_name == "images"
    assert info.output_name == "scores"
    assert info.input_shape == (1, 3, 224, 224)


def test_load_initializes_and_reuses_onnx_session(monkeypatch, tmp_path):
    artifact = tmp_path / "model.onnx"
    artifact.write_bytes(b"mock model marker")
    fake_session = FakeSession(np.array([[0.01] * 8], dtype=np.float32))
    ort = SimpleNamespace(InferenceSession=lambda *_args, **_kwargs: fake_session)
    monkeypatch.setitem(sys.modules, "onnxruntime", ort)
    model = VisionClassifier(artifact)
    assert model.load() is True
    assert model.ready is True
    assert model.diagnostic_status == "ready"
    assert model.load() is True


def test_onnx_initialization_rejects_unexpected_output_shape(tmp_path):
    model = VisionClassifier(tmp_path / "model.onnx")
    session = FakeSession(np.array([[0.01] * 8], dtype=np.float32))
    session.get_outputs = lambda: [SimpleNamespace(name="scores", shape=[1, 7], type="tensor(float)")]
    with pytest.raises(RuntimeError, match="class count"):
        model._create_session(tmp_path / "model.onnx", FakeOrt(session))


def test_model_initialization_failure_is_safe(monkeypatch, tmp_path):
    model = VisionClassifier(tmp_path / "missing.onnx")
    monkeypatch.setattr(model, "_download_artifact", lambda *_args: (_ for _ in ()).throw(RuntimeError("private/path")))
    assert model.load() is False
    assert model.ready is False
    assert model.diagnostic_status == "initialization_failed"


@pytest.mark.parametrize(
    ("class_name", "category"),
    [
        ("battery", "hazardous"),
        ("biological", "biodegradable"),
        ("cardboard", "recyclable"),
        ("glass", "recyclable"),
        ("metal", "recyclable"),
        ("paper", "recyclable"),
        ("plastic", "recyclable"),
    ],
)
def test_documented_classes_map_conservatively(class_name, category):
    scores = np.full(8, 0.01, dtype=np.float32)
    scores[CLASS_NAMES.index(class_name)] = 0.93
    model, session = model_with_scores(scores)
    prediction = model.predict(Image.new("RGB", (32, 40), color="blue"))
    assert prediction.predicted_category == category
    assert prediction.predicted_item == CLASS_POLICIES[class_name][0]
    assert prediction.classification_status == "success"
    names, feed = session.feed
    tensor = feed["images"]
    assert names == ["scores"]
    assert tensor.shape == (1, 3, 224, 224)
    assert tensor.dtype == np.float32
    assert 0.0 <= tensor.min() <= tensor.max() <= 1.0


@pytest.mark.parametrize("class_name", ["trash", "plastic"])
def test_trash_and_weak_margin_are_uncertain(class_name):
    scores = np.full(8, 0.01, dtype=np.float32)
    if class_name == "trash":
        scores[CLASS_NAMES.index("trash")] = 0.93
    else:
        scores[:] = 0.015
        scores[CLASS_NAMES.index("plastic")] = 0.48
        scores[CLASS_NAMES.index("glass")] = 0.43
    model, _ = model_with_scores(scores)
    prediction = model.predict(Image.new("RGB", (20, 20)))
    assert prediction.classification_status == "uncertain"
    assert prediction.predicted_item is None
    assert prediction.predicted_category is None
    assert prediction.manual_review_recommended is True


def test_invalid_model_scores_raise_inference_error():
    scores = np.zeros(8, dtype=np.float32)
    scores[0] = np.nan
    model, _ = model_with_scores(scores)
    with pytest.raises(RuntimeError, match="invalid class scores"):
        model.predict(Image.new("RGB", (20, 20)))


def test_missing_and_corrupt_artifacts_report_download_failure(monkeypatch, tmp_path):
    model = VisionClassifier(tmp_path / "missing.onnx")
    monkeypatch.setattr(model, "_download_artifact", lambda *_args: (_ for _ in ()).throw(ModelDownloadError("offline")))
    assert model.load() is False
    assert model.diagnostic_status == "model_download_failed"

    corrupt = tmp_path / "corrupt.onnx"
    corrupt.write_bytes(b"not an onnx model")
    model = VisionClassifier(corrupt)
    monkeypatch.setattr(model, "_create_session", lambda *_args: (_ for _ in ()).throw(ValueError("invalid")))
    monkeypatch.setattr(model, "_download_artifact", lambda *_args: (_ for _ in ()).throw(ModelDownloadError("offline")))
    assert model.load() is False
    assert model.diagnostic_status == "model_download_failed"


def test_model_download_failure_is_safe(monkeypatch, tmp_path):
    model = VisionClassifier(tmp_path / "missing.onnx")
    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(ModelDownloadError):
        model._download_artifact(model.model_path, FakeOrt(FakeSession(np.ones((1, 8)))))


async def api_request(method: str, path: str, **kwargs) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.anyio
async def test_health_is_independent_of_model():
    result = await api_request("GET", "/api/health")
    assert result.json() == {"status": "ok"}


@pytest.mark.anyio
async def test_model_status(vision_ready):
    result = await api_request("GET", "/api/model/status")
    assert result.status_code == 200
    assert result.json() == {
        "initialized_successfully": True,
        "model_identifier": classifier.model_identifier,
        "inference_available": True,
        "diagnostic_status": "ready",
    }


@pytest.mark.anyio
async def test_model_status_reports_unavailable_safely(monkeypatch):
    monkeypatch.setattr(classifier, "_session_info", None)
    monkeypatch.setattr(classifier, "_diagnostic_status", "model_download_failed")
    result = await api_request("GET", "/api/model/status")
    assert result.json() == {
        "initialized_successfully": False,
        "model_identifier": classifier.model_identifier,
        "inference_available": False,
        "diagnostic_status": "model_download_failed",
    }


@pytest.mark.anyio
async def test_valid_upload_uses_classifier_and_returns_contract(vision_ready):
    result = await api_request(
        "POST", "/api/scans", files={"file": ("ignored-name.jpg", jpeg_bytes(), "text/plain")}
    )
    assert result.status_code == 200
    validated = ClassificationResponse.model_validate(result.json())
    assert validated.predicted_item == "Plastic"
    assert validated.predicted_category == "recyclable"
    assert validated.scan_id
    assert validated.model_identifier == classifier.model_identifier


@pytest.mark.anyio
async def test_invalid_image_is_rejected(vision_ready):
    result = await api_request("POST", "/api/scans", files={"file": ("image.jpg", b"not an image", "image/jpeg")})
    assert result.status_code == 422


@pytest.mark.anyio
async def test_unsupported_image_format_is_rejected(vision_ready):
    stream = BytesIO()
    Image.new("RGB", (64, 64), color="blue").save(stream, format="GIF")
    result = await api_request("POST", "/api/scans", files={"file": ("image.gif", stream.getvalue(), "image/gif")})
    assert result.status_code == 415


@pytest.mark.anyio
async def test_empty_upload_is_rejected(vision_ready):
    result = await api_request("POST", "/api/scans", files={"file": ("empty.jpg", b"", "image/jpeg")})
    assert result.status_code == 422


@pytest.mark.anyio
async def test_oversized_upload_is_rejected(vision_ready):
    result = await api_request(
        "POST", "/api/scans", files={"file": ("large.jpg", b"x" * (8 * 1024 * 1024 + 1), "image/jpeg")}
    )
    assert result.status_code == 413


@pytest.mark.anyio
async def test_uncertain_prediction_has_null_category_and_requests_review(vision_ready, monkeypatch):
    uncertain = VisionPrediction(None, None, 0.24, True, "Please have the item reviewed.", "Threshold not met.", "uncertain")
    monkeypatch.setattr(classifier, "predict", lambda _image: uncertain)
    result = await api_request("POST", "/api/scans", files={"file": ("image.jpg", jpeg_bytes(), "image/jpeg")})
    assert result.status_code == 200
    body = ClassificationResponse.model_validate(result.json())
    assert body.classification_status == "uncertain"
    assert body.predicted_category is None
    assert body.predicted_item is None
    assert body.manual_review_recommended is True


@pytest.mark.anyio
async def test_model_unavailable_returns_503(vision_ready, monkeypatch):
    monkeypatch.setattr(classifier, "_session_info", None)
    result = await api_request("POST", "/api/scans", files={"file": ("image.jpg", jpeg_bytes(), "image/jpeg")})
    assert result.status_code == 503


@pytest.mark.anyio
async def test_inference_exception_returns_503_without_success(vision_ready, monkeypatch):
    monkeypatch.setattr(classifier, "predict", lambda _image: (_ for _ in ()).throw(RuntimeError("secret/path")))
    result = await api_request("POST", "/api/scans", files={"file": ("image.jpg", jpeg_bytes(), "image/jpeg")})
    assert result.status_code == 503
    assert "secret/path" not in result.text
    assert "classification" in result.json()["detail"]
