"""CPU ONNX object detection for mixed-waste scenes.

Why this module exists
----------------------
:mod:`backend.app.vision` runs a whole-image, single-label material classifier:
one image in, one score vector out. That model cannot report *how many* items a
photo contains, *where* they are, or that two different materials are present at
once, so it must never be presented as a multi-object detector.

This module adds a genuinely separate capability: a pretrained Ultralytics
YOLO11n detector that was fine-tuned on waste imagery and reports per-object
bounding boxes with material-level labels (glass, metal, paper, plastic, trash).

Object identity and material classification remain separate concerns:

* this detector answers "where are the objects, and what material does each
  region look like";
* ``backend.app.vision`` can be run on an individual crop as an independent
  cross-check (see :mod:`backend.app.services.batch_scan_service`).

Model provenance and licence
----------------------------
* source: https://huggingface.co/Jeremy341/MIRA-AI (file ``mira_exp019.onnx``)
* the repository card states MIT, but the artifact's own embedded ONNX metadata
  declares ``AGPL-3.0 License (https://ultralytics.com/license)``, inherited from
  the Ultralytics YOLO11 training stack. The embedded metadata is what the file
  actually carries, so ``DETECTOR_LICENSE`` reports it and deployment of this
  artifact must be reviewed before any release. See ``DETECTOR_LICENSE``.

Only inference is performed here. No training or fine-tuning happens in this
project, and no accuracy figure is claimed: the model was not evaluated against
a representative labelled waste set by this project.
"""

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

DETECTOR_IDENTIFIER = "mira-exp019-waste-yolo11n"
DETECTOR_SOURCE = "https://huggingface.co/Jeremy341/MIRA-AI"
DETECTOR_MODEL_URL = (
    "https://huggingface.co/Jeremy341/MIRA-AI/resolve/main/mira_exp019.onnx"
)
DETECTOR_LICENSE = (
    "AGPL-3.0 (declared in the ONNX artifact metadata; the Hugging Face model card "
    "states MIT). Review before deploying."
)
DETECTOR_ARCHITECTURE = "Ultralytics YOLO11n detect head, exported to ONNX by training stack 8.4.112"

DEFAULT_DETECTOR_PATH = Path(__file__).resolve().parents[1] / "models" / "waste-detector.onnx"

DETECTOR_INPUT_SIZE = (640, 640)
# Class order is fixed by the artifact: metadata records {0: glass, 1: metal,
# 2: paper, 3: plastic, 4: trash}. load() verifies the output width matches.
DETECTOR_CLASS_NAMES = ("glass", "metal", "paper", "plastic", "trash")
MAX_DETECTOR_BYTES = 64 * 1024 * 1024
LETTERBOX_PAD_VALUE = 114

# Detection decoding policy. These are detector-operating thresholds, not
# accuracy guarantees, and they are deliberately separate from the whole-image
# classifier's uncertainty thresholds in ``vision.py`` because the two models
# have different score distributions.
DETECTION_SCORE_THRESHOLD = 0.20
NMS_IOU_THRESHOLD = 0.45
# Two boxes of *different* classes that overlap this heavily describe one
# physical object, not two. Measured on this artifact: the same glass jar was
# returned as both ``metal`` 0.60 and ``glass`` 0.54 at IoU 0.99. Such a pair is
# collapsed into one detection and the losing label is kept as an alternate so
# the disagreement can still drive a review request.
SAME_OBJECT_IOU_THRESHOLD = 0.75
MAX_DETECTIONS_PER_SCENE = 24


class DetectorArtifactError(RuntimeError):
    """The local or downloaded detector ONNX artifact could not be validated."""


class DetectorDownloadError(RuntimeError):
    """A safe detector artifact download could not be completed."""


@dataclass(frozen=True)
class Detection:
    """One detected object in one image.

    ``box`` is ``(x1, y1, x2, y2)`` in pixels of the *original* uploaded image,
    already mapped back out of letterbox space. ``class_scores`` holds every
    class score for this object, highest first, so callers can inspect the
    runner-up instead of trusting only the argmax. ``alternate_labels`` holds
    labels from separate boxes that were collapsed into this one because they
    described the same physical object.
    """

    class_name: str
    score: float
    box: tuple[float, float, float, float]
    class_scores: tuple[tuple[str, float], ...] = ()
    alternate_labels: tuple[tuple[str, float], ...] = ()

    @property
    def runner_up(self) -> tuple[str, float] | None:
        """Strongest competing material label from any source, or ``None``.

        Considers both the runner-up class inside this box's own score vector
        and any alternate label contributed by a collapsed duplicate box, so an
        object that looks like two materials is reported as ambiguous.
        """
        candidates = [
            (name, score)
            for name, score in (*self.class_scores[1:], *self.alternate_labels)
            if name != self.class_name
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda candidate: candidate[1])

    @property
    def margin(self) -> float | None:
        """Score gap to the strongest competing label, or ``None`` if unavailable."""
        runner_up = self.runner_up
        if runner_up is None:
            return None
        return float(self.score - runner_up[1])


@dataclass(frozen=True)
class _SessionInfo:
    session: Any
    input_name: str
    output_name: str
    input_shape: tuple[Any, ...]


def _compute_letterbox(image: Image.Image, size: tuple[int, int] = DETECTOR_INPUT_SIZE) -> tuple[Image.Image, float, int, int]:
    """Resize with aspect ratio preserved and pad to a square canvas.

    Returns the padded canvas, the uniform gain applied, and the padding offsets.
    This mirrors the Ultralytics letterbox convention the artifact was trained
    with, and the inverse mapping in :meth:`WasteDetector.detect` uses the same
    gain and offsets so boxes land back on the original pixels.
    """
    target_w, target_h = size
    source_w, source_h = image.size
    gain = min(target_w / source_w, target_h / source_h)
    scaled_w = int(round(source_w * gain))
    scaled_h = int(round(source_h * gain))
    resized = image.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (target_w, target_h), (LETTERBOX_PAD_VALUE,) * 3)
    offset_x = (target_w - scaled_w) // 2
    offset_y = (target_h - scaled_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas, gain, offset_x, offset_y


def _intersection_over_union(
    box: tuple[float, float, float, float], others: Any
) -> Any:
    """IoU between one box and an ``(N, 4)`` array of boxes (numpy in, numpy out)."""
    import numpy as np

    x1 = np.maximum(box[0], others[:, 0])
    y1 = np.maximum(box[1], others[:, 1])
    x2 = np.minimum(box[2], others[:, 2])
    y2 = np.minimum(box[3], others[:, 3])
    intersection = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    first_area = (box[2] - box[0]) * (box[3] - box[1])
    other_areas = (others[:, 2] - others[:, 0]) * (others[:, 3] - others[:, 1])
    union = first_area + other_areas - intersection
    return intersection / np.maximum(union, 1e-9)


def _non_maximum_suppression(
    boxes: Any, scores: Any, iou_threshold: float
) -> list[int]:
    """Single-class greedy NMS returning kept indices."""
    import numpy as np

    if boxes.shape[0] == 0:
        return []
    order = np.argsort(scores)[::-1]
    keep: list[int] = []
    while order.size > 0:
        current = int(order[0])
        keep.append(current)
        if order.size == 1:
            break
        remaining = order[1:]
        iou = _intersection_over_union(boxes[current], boxes[remaining])
        order = remaining[iou <= iou_threshold]
    return keep


class WasteDetector:
    """Loads one local ONNX Runtime CPU detection session and reuses it."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        configured_path = model_path or os.getenv("DETECTOR_MODEL_PATH")
        if configured_path is None:
            self.model_path = DEFAULT_DETECTOR_PATH
        else:
            path = Path(configured_path)
            self.model_path = path if path.is_absolute() else DEFAULT_DETECTOR_PATH.parents[1] / path
        self.model_identifier = DETECTOR_IDENTIFIER
        self.license = DETECTOR_LICENSE
        self.source = DETECTOR_SOURCE
        self.class_names = DETECTOR_CLASS_NAMES
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
            raise DetectorArtifactError("ONNX Runtime CPU provider is unavailable")

        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1:
            raise DetectorArtifactError("Unexpected ONNX detector input or output count")

        input_meta = inputs[0]
        output_meta = outputs[0]
        shape = tuple(input_meta.shape)
        output_shape = tuple(output_meta.shape)

        if input_meta.type != "tensor(float)" or len(shape) != 4:
            raise DetectorArtifactError("Detector ONNX input must be a float NCHW image tensor")
        if isinstance(shape[0], int) and shape[0] != 1:
            raise DetectorArtifactError("Detector ONNX batch dimension must be one")
        if isinstance(shape[1], int) and shape[1] != 3:
            raise DetectorArtifactError("Detector ONNX input does not have three RGB channels")
        if any(
            isinstance(dim, int) and dim != expected
            for dim, expected in zip(shape[2:], DETECTOR_INPUT_SIZE)
        ):
            raise DetectorArtifactError("Detector ONNX input size differs from the documented 640x640")
        if output_meta.type != "tensor(float)" or len(output_shape) != 3:
            raise DetectorArtifactError("Detector ONNX output must be a float detection tensor")
        # YOLO11 detect head emits (batch, 4 + classes, anchors). Requiring the
        # exact width ties the class list in this module to the artifact itself.
        if (
            isinstance(output_shape[1], int)
            and output_shape[1] != 4 + len(DETECTOR_CLASS_NAMES)
        ):
            raise DetectorArtifactError(
                "Detector ONNX class count does not match the documented waste class list"
            )
        if isinstance(output_shape[0], int) and output_shape[0] != 1:
            raise DetectorArtifactError("Detector ONNX output batch dimension must be one")

        logger.info(
            "Detector ONNX metadata: input=%s shape=%s output=%s shape=%s providers=%s",
            input_meta.name,
            shape,
            output_meta.name,
            output_shape,
            providers,
        )
        return _SessionInfo(session, input_meta.name, output_meta.name, shape)

    def _download_artifact(self, target: Path, ort: Any) -> _SessionInfo:
        """Download, validate, and only then atomically publish the artifact."""
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            request = urllib.request.Request(
                DETECTOR_MODEL_URL,
                headers={"User-Agent": "Smart-Recycling-Agent/1.0"},
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                status = getattr(response, "status", 200)
                if status != 200:
                    raise DetectorDownloadError(f"Detector download returned HTTP {status}")
                declared_length = response.headers.get("Content-Length")
                expected_length = int(declared_length) if declared_length else None
                if expected_length is not None and expected_length > MAX_DETECTOR_BYTES:
                    raise DetectorDownloadError("Detector artifact exceeds the permitted size")

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
                        if downloaded > MAX_DETECTOR_BYTES:
                            raise DetectorDownloadError("Detector artifact exceeds the permitted size")
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

            if downloaded == 0:
                raise DetectorDownloadError("Detector download returned an empty artifact")
            if expected_length is not None and downloaded != expected_length:
                raise DetectorDownloadError("Detector download was incomplete")

            # Parse the temporary ONNX file before it can become the valid target.
            session_info = self._create_session(temporary_path, ort)
            os.replace(temporary_path, target)
            temporary_path = None
            return session_info
        except DetectorDownloadError:
            raise
        except urllib.error.HTTPError as exc:
            raise DetectorDownloadError(f"Detector download returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            raise DetectorDownloadError(f"Detector download failed ({type(exc).__name__})") from None
        except Exception as exc:
            raise DetectorArtifactError(
                f"Downloaded detector ONNX artifact was invalid ({type(exc).__name__})"
            ) from None
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove incomplete detector model temporary file")

    def load(self) -> bool:
        """Validate or download the detector artifact and initialize CPU inference once."""
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
                    logger.warning(
                        "Existing detector ONNX artifact failed validation (%s)", type(exc).__name__
                    )
                    session_info = self._download_artifact(self.model_path, ort)
            else:
                session_info = self._download_artifact(self.model_path, ort)
            self._session_info = session_info
            self._diagnostic_status = "ready"
            return True
        except ImportError as exc:
            self._session_info = None
            self._diagnostic_status = "runtime_unavailable"
            logger.warning("ONNX detection runtime is unavailable (%s)", type(exc).__name__)
            return False
        except DetectorDownloadError as exc:
            self._session_info = None
            self._diagnostic_status = "model_download_failed"
            logger.warning("Detector model download failed (%s)", str(exc))
            return False
        except DetectorArtifactError as exc:
            self._session_info = None
            self._diagnostic_status = "model_invalid"
            logger.warning("Detector ONNX artifact is invalid (%s)", str(exc))
            return False
        except Exception as exc:
            self._session_info = None
            self._diagnostic_status = "initialization_failed"
            logger.warning("Detector initialization failed (%s)", type(exc).__name__)
            return False

    def detect(
        self,
        image: Image.Image,
        score_threshold: float = DETECTION_SCORE_THRESHOLD,
        iou_threshold: float = NMS_IOU_THRESHOLD,
    ) -> list[Detection]:
        """Return real per-object detections for one image.

        Returns an empty list when the model finds nothing above threshold. An
        empty list is a real result and is never substituted with a stand-in
        detection derived from a whole-image label.
        """
        if self._session_info is None:
            raise RuntimeError("Waste detector is unavailable")

        import numpy as np

        session_info = self._session_info
        rgb = image.convert("RGB")
        canvas, gain, offset_x, offset_y = _compute_letterbox(rgb)
        pixels = np.asarray(canvas, dtype=np.float32) / np.float32(255.0)
        tensor = np.transpose(pixels, (2, 0, 1))[np.newaxis, ...].astype(np.float32, copy=False)

        raw_output = session_info.session.run(
            [session_info.output_name],
            {session_info.input_name: tensor},
        )
        if len(raw_output) != 1:
            raise RuntimeError("Detector inference returned an unexpected output count")

        predictions = np.asarray(raw_output[0], dtype=np.float32)
        if predictions.shape[0] != 1 or predictions.ndim != 3:
            raise RuntimeError("Detector inference returned an unexpected output shape")
        predictions = predictions[0]  # (4 + classes, anchors)
        if predictions.shape[0] != 4 + len(DETECTOR_CLASS_NAMES):
            raise RuntimeError("Detector inference returned an unexpected class count")

        centers = predictions[:4].T          # (anchors, 4) as cx, cy, w, h
        class_scores = predictions[4:].T     # (anchors, classes)
        if not np.all(np.isfinite(centers)) or not np.all(np.isfinite(class_scores)):
            raise RuntimeError("Detector inference returned non-finite values")

        best_scores = class_scores.max(axis=1)
        best_indices = class_scores.argmax(axis=1)
        selected = np.where(best_scores >= score_threshold)[0]
        if selected.size == 0:
            return []

        boxes = np.empty((selected.size, 4), dtype=np.float32)
        boxes[:, 0] = centers[selected, 0] - centers[selected, 2] / 2.0
        boxes[:, 1] = centers[selected, 1] - centers[selected, 3] / 2.0
        boxes[:, 2] = centers[selected, 0] + centers[selected, 2] / 2.0
        boxes[:, 3] = centers[selected, 1] + centers[selected, 3] / 2.0
        scores = best_scores[selected]
        class_ids = best_indices[selected]

        # Class-aware NMS, matching the Ultralytics default of suppressing only
        # within the same class. Two materials overlapping in a scene are kept.
        kept_local: list[int] = []
        for class_id in np.unique(class_ids):
            class_members = np.where(class_ids == class_id)[0]
            for offset in _non_maximum_suppression(
                boxes[class_members], scores[class_members], iou_threshold
            ):
                kept_local.append(int(class_members[offset]))

        image_width, image_height = rgb.size
        candidates: list[Detection] = []
        for local_index in kept_local:
            global_index = int(selected[local_index])
            x1 = max(0.0, min(float(image_width), (float(boxes[local_index, 0]) - offset_x) / gain))
            y1 = max(0.0, min(float(image_height), (float(boxes[local_index, 1]) - offset_y) / gain))
            x2 = max(0.0, min(float(image_width), (float(boxes[local_index, 2]) - offset_x) / gain))
            y2 = max(0.0, min(float(image_height), (float(boxes[local_index, 3]) - offset_y) / gain))
            if x2 <= x1 or y2 <= y1:
                continue

            class_index = int(class_ids[local_index])
            ordered = np.argsort(class_scores[global_index])[::-1]
            candidates.append(
                Detection(
                    class_name=DETECTOR_CLASS_NAMES[class_index],
                    score=float(scores[local_index]),
                    box=(x1, y1, x2, y2),
                    class_scores=tuple(
                        (DETECTOR_CLASS_NAMES[int(candidate)], float(class_scores[global_index][candidate]))
                        for candidate in ordered
                    ),
                )
            )

        detections = _collapse_same_object_duplicates(candidates)
        if len(detections) > MAX_DETECTIONS_PER_SCENE:
            logger.info(
                "Detector returned %d objects; truncating to the configured maximum", len(detections)
            )
            detections = detections[:MAX_DETECTIONS_PER_SCENE]
        return detections


def _collapse_same_object_duplicates(candidates: list[Detection]) -> list[Detection]:
    """Collapse cross-class boxes that describe one physical object.

    Class-aware NMS in :meth:`WasteDetector.detect` intentionally keeps
    overlapping boxes whose labels differ, because two materials genuinely can
    overlap. That also means a single object can be returned twice with two
    labels. Anything overlapping a stronger box above
    ``SAME_OBJECT_IOU_THRESHOLD`` is treated as one object: the strongest label
    wins and the losing labels are attached as alternates for review.
    """
    import numpy as np

    ordered = sorted(candidates, key=lambda detection: detection.score, reverse=True)
    kept: list[Detection] = []
    kept_boxes: list[tuple[float, float, float, float]] = []
    for detection in ordered:
        if kept_boxes:
            overlaps = _intersection_over_union(detection.box, np.asarray(kept_boxes, dtype=np.float32))
            duplicate_of = int(np.argmax(overlaps)) if float(overlaps.max()) >= SAME_OBJECT_IOU_THRESHOLD else None
        else:
            duplicate_of = None

        if duplicate_of is None:
            kept.append(detection)
            kept_boxes.append(detection.box)
            continue

        winner = kept[duplicate_of]
        kept[duplicate_of] = Detection(
            class_name=winner.class_name,
            score=winner.score,
            box=winner.box,
            class_scores=winner.class_scores,
            alternate_labels=(*winner.alternate_labels, (detection.class_name, detection.score)),
        )

    return kept


detector = WasteDetector()
