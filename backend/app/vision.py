"""CPU ONNX inference and conservative waste-material routing suggestions."""

from __future__ import annotations

import logging
import os
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from PIL import Image

logger = logging.getLogger(__name__)
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL_IDENTIFIER = "SriramRokkam/wastewise-garbage-cls"
MODEL_URL = (
    "https://huggingface.co/SriramRokkam/wastewise-garbage-cls/resolve/main/"
    "wastewise-yolo.onnx"
)
MODEL_INPUT_SIZE = (224, 224)
MAX_MODEL_BYTES = 64 * 1024 * 1024
SCORE_THRESHOLD = 0.45
MARGIN_THRESHOLD = 0.12
CLASS_NAMES = (
    "battery",
    "biological",
    "cardboard",
    "glass",
    "metal",
    "paper",
    "plastic",
    "trash",
)

# Model materials and application policy are intentionally separate.
CLASS_POLICIES: dict[str, tuple[str, str, str]] = {
    "battery": (
        "Battery",
        "hazardous",
        "Use an authorized battery collection or hazardous-waste service. Do not place in curbside recycling or general waste unless local rules explicitly permit it; protect terminals where required.",
    ),
    "biological": (
        "Biological waste",
        "biodegradable",
        "Use a local food-scrap or compost program if available; accepted materials vary by program.",
    ),
    "cardboard": (
        "Cardboard",
        "recyclable",
        "Recycle only if locally accepted; keep cardboard clean and dry.",
    ),
    "glass": (
        "Glass",
        "recyclable",
        "Check local glass acceptance. The model cannot determine whether an object is clean, intact, reusable, or accepted locally.",
    ),
    "metal": (
        "Metal",
        "recyclable",
        "Check local metal acceptance and follow local preparation rules. This material label does not identify electronic waste.",
    ),
    "paper": (
        "Paper",
        "recyclable",
        "Recycle only if locally accepted; keep paper clean and dry.",
    ),
    "plastic": (
        "Plastic",
        "recyclable",
        "Check local plastic acceptance and preparation rules. This material label does not identify electronic waste.",
    ),
}

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "wastewise-yolo.onnx"


class ModelArtifactError(RuntimeError):
    """The local or downloaded ONNX artifact could not be validated."""


class ModelDownloadError(RuntimeError):
    """A safe model artifact download could not be completed."""


@dataclass(frozen=True)
class VisionPrediction:
    predicted_item: str | None
    predicted_category: str | None
    match_score: float | None
    manual_review_recommended: bool
    suggested_route: str
    explanation: str
    classification_status: str


@dataclass(frozen=True)
class _SessionInfo:
    session: Any
    input_name: str
    output_name: str
    input_shape: tuple[Any, ...]


class VisionClassifier:
    """Loads one local ONNX Runtime CPU session and reuses it for scans."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        configured_path = model_path or os.getenv("VISION_MODEL_PATH")
        if configured_path is None:
            self.model_path = DEFAULT_MODEL_PATH
        else:
            path = Path(configured_path)
            self.model_path = path if path.is_absolute() else DEFAULT_MODEL_PATH.parents[1] / path
        self.model_identifier = MODEL_IDENTIFIER
        self._session_info: _SessionInfo | None = None
        self._diagnostic_status = "not_initialized"

    @property
    def ready(self) -> bool:
        return self._session_info is not None

    @property
    def diagnostic_status(self) -> str:
        return self._diagnostic_status

    def _create_session(self, artifact_path: Path, ort: Any) -> _SessionInfo:
        session = ort.InferenceSession(str(artifact_path), providers=["CPUExecutionProvider"])
        providers = session.get_providers()
        if "CPUExecutionProvider" not in providers:
            raise ModelArtifactError("ONNX Runtime CPU provider is unavailable")

        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1:
            raise ModelArtifactError("Unexpected ONNX input or output count")

        input_meta = inputs[0]
        output_meta = outputs[0]
        shape = tuple(input_meta.shape)
        output_shape = tuple(output_meta.shape)
        if input_meta.type != "tensor(float)" or len(shape) != 4:
            raise ModelArtifactError("ONNX input must be a float NCHW image tensor")
        if isinstance(shape[1], int) and shape[1] != 3:
            raise ModelArtifactError("ONNX input does not have three RGB channels")
        if any(isinstance(dim, int) and dim != expected for dim, expected in zip(shape[2:], MODEL_INPUT_SIZE)):
            raise ModelArtifactError("ONNX input dimensions differ from the documented 224x224 size")
        if output_meta.type != "tensor(float)" or len(output_shape) not in (1, 2):
            raise ModelArtifactError("ONNX output must be a float class-score tensor")
        if output_shape[-1] != len(CLASS_NAMES):
            raise ModelArtifactError("ONNX output class count does not match the documented class list")
        if len(output_shape) == 2 and isinstance(output_shape[0], int) and output_shape[0] != 1:
            raise ModelArtifactError("ONNX output batch dimension must be one")

        logger.info(
            "ONNX model metadata: input=%s shape=%s output=%s shape=%s providers=%s",
            input_meta.name,
            shape,
            output_meta.name,
            output_shape,
            providers,
        )
        return _SessionInfo(session, input_meta.name, output_meta.name, shape)

    def _download_artifact(self, target: Path, ort: Any) -> _SessionInfo:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            request = urllib.request.Request(
                MODEL_URL,
                headers={"User-Agent": "Smart-Recycling-Agent/1.0"},
            )
            with urllib.request.urlopen(request, timeout=120) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise ModelDownloadError(f"Model download returned HTTP {status}")
                declared_length = response.headers.get("Content-Length")
                expected_length = int(declared_length) if declared_length else None
                if expected_length is not None and expected_length > MAX_MODEL_BYTES:
                    raise ModelDownloadError("Model artifact exceeds the permitted size")

                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{target.name}.",
                    suffix=".part",
                    dir=target.parent,
                    delete=False,
                ) as output:
                    temporary_path = Path(output.name)
                    downloaded = 0
                    while chunk := response.read(1024 * 1024):
                        downloaded += len(chunk)
                        if downloaded > MAX_MODEL_BYTES:
                            raise ModelDownloadError("Model artifact exceeds the permitted size")
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

            if downloaded == 0:
                raise ModelDownloadError("Model download returned an empty artifact")
            if expected_length is not None and downloaded != expected_length:
                raise ModelDownloadError("Model download was incomplete")

            # Parse the temporary ONNX file before it can become the valid target.
            session_info = self._create_session(temporary_path, ort)
            os.replace(temporary_path, target)
            temporary_path = None
            return session_info
        except ModelDownloadError:
            raise
        except urllib.error.HTTPError as exc:
            raise ModelDownloadError(f"Model download returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise ModelDownloadError(f"Model download failed ({type(exc).__name__})") from None
        except Exception as exc:
            raise ModelArtifactError(f"Downloaded ONNX artifact was invalid ({type(exc).__name__})") from None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove incomplete model temporary file")

    def load(self) -> bool:
        """Validate or download the artifact and initialize CPU inference once."""
        if self.ready:
            return True
        self._diagnostic_status = "initializing"
        try:
            import numpy  # noqa: F401
            import onnxruntime as ort

            if self.model_path.is_file():
                try:
                    session_info = self._create_session(self.model_path, ort)
                except Exception as exc:
                    logger.warning("Existing ONNX artifact failed validation (%s)", type(exc).__name__)
                    session_info = self._download_artifact(self.model_path, ort)
            else:
                session_info = self._download_artifact(self.model_path, ort)
            self._session_info = session_info
            self._diagnostic_status = "ready"
            return True
        except ImportError as exc:
            self._session_info = None
            self._diagnostic_status = "runtime_unavailable"
            logger.warning("ONNX inference runtime is unavailable (%s)", type(exc).__name__)
            return False
        except ModelDownloadError as exc:
            self._session_info = None
            self._diagnostic_status = "model_download_failed"
            logger.warning("ONNX model download failed (%s)", str(exc))
            return False
        except ModelArtifactError as exc:
            self._session_info = None
            self._diagnostic_status = "model_invalid"
            logger.warning("ONNX model artifact is invalid (%s)", str(exc))
            return False
        except Exception as exc:
            self._session_info = None
            self._diagnostic_status = "initialization_failed"
            logger.warning("ONNX model initialization failed (%s)", type(exc).__name__)
            return False

    def predict(self, image: Image.Image) -> VisionPrediction:
        if self._session_info is None:
            raise RuntimeError("Vision model is unavailable")

        # Keep process health and API startup independent of model dependencies.
        import numpy as np

        session_info = self._session_info
        resized = image.convert("RGB").resize(MODEL_INPUT_SIZE, Image.Resampling.BILINEAR)
        pixels = np.asarray(resized, dtype=np.float32) / np.float32(255.0)
        tensor = np.transpose(pixels, (2, 0, 1))[np.newaxis, ...].astype(np.float32, copy=False)
        output_values = session_info.session.run(
            [session_info.output_name],
            {session_info.input_name: tensor},
        )
        if len(output_values) != 1:
            raise RuntimeError("ONNX inference returned an unexpected output count")
        scores = np.asarray(output_values[0], dtype=np.float32)
        if scores.size != len(CLASS_NAMES) or not np.all(np.isfinite(scores)):
            raise RuntimeError("ONNX inference returned invalid class scores")
        scores = scores.reshape(-1)
        if np.any(scores < 0.0) or np.any(scores > 1.0) or not np.isclose(float(scores.sum()), 1.0, atol=1e-3):
            raise RuntimeError("ONNX scores did not match the documented softmax output")

        order = np.argsort(scores)
        class_index = int(order[-1])
        score = float(scores[class_index])
        margin = score - float(scores[int(order[-2])])
        class_name = CLASS_NAMES[class_index]
        uncertain = (
            class_name not in CLASS_POLICIES
            or score < SCORE_THRESHOLD
            or margin < MARGIN_THRESHOLD
        )
        if uncertain:
            reason = "The model's top class was trash or did not clear the configured score and margin heuristics."
            return VisionPrediction(
                predicted_item=None,
                predicted_category=None,
                match_score=score,
                manual_review_recommended=True,
                suggested_route="Please request manual review and follow local waste-authority guidance.",
                explanation=(
                    f"{reason} These thresholds are heuristics, not an accuracy guarantee. "
                    "This model has no dedicated electronic-waste class and cannot verify local acceptance or item condition."
                ),
                classification_status="uncertain",
            )

        item, category, route = CLASS_POLICIES[class_name]
        return VisionPrediction(
            predicted_item=item,
            predicted_category=category,
            match_score=score,
            manual_review_recommended=False,
            suggested_route=route,
            explanation=(
                f"The ONNX model's top material class was {class_name} (model score {score:.3f}). "
                "This score is not a guaranteed probability of correctness. The model has no dedicated "
                "electronic-waste class and cannot verify local acceptance, contamination, or item condition."
            ),
            classification_status="success",
        )


classifier = VisionClassifier()
