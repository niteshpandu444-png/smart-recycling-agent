"""Per-object analysis for mixed-waste scenes.

This service turns raw detector output (:mod:`backend.app.vision_detector`) into
per-item, reviewable decisions. It keeps three things strictly separate, because
collapsing them is how a demo starts lying:

``detected``
    The detector saw an object at a location with a material label. Nothing has
    been stored as inventory and nothing is confirmed.
``needs_review``
    A documented reason says the label should not be trusted without a human.
``confirmed``
    Only ever set by the existing confirmation workflow in
    :mod:`backend.app.services.material_service` after an explicit user action.

The module deliberately has no dependency on the FastAPI app or on the ONNX
runtimes so that its decision logic can be unit-tested with synthetic detections
and no model file present.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Sequence

from PIL import Image

from backend.app.services.routing_rules import (
    HOLDING_BIN_ID,
    MARGIN_THRESHOLD,
    is_confusable_pair,
    resolve_destination,
)
from backend.app.vision import CLASS_POLICIES, PERSISTED_CATEGORY_BY_MODEL_CLASS

logger = logging.getLogger("smart_recycling.batch_scan_service")

# Detector material classes to application categories. The detector reports
# material appearance only; it has no battery, organic, or e-waste class, so
# those application categories are simply not reachable from this path.
DETECTOR_CLASS_TO_APP_CATEGORY: dict[str, str] = {
    "glass": "glass",
    "metal": "metal",
    "paper": "paper",
    "plastic": "plastic",
    "trash": "holding",
}

# Guidance for the detector's residual ``trash`` class, which is not a policy
# entry in ``CLASS_POLICIES``.
UNSUPPORTED_CLASS_GUIDANCE = (
    "The detector grouped this object as generic trash and no material-specific handling could be "
    "established. Request manual review and follow local waste-authority guidance."
)

# Below this detector score an object is still surfaced (dropping it would hide
# real items) but is explicitly marked for review. This is a detector-operating
# threshold, not a calibrated probability.
REVIEW_SCORE_THRESHOLD = 0.50

# A crop smaller than this cannot be meaningfully re-examined by the whole-image
# classifier, so the cross-check is skipped and recorded in item metadata.
CROSS_CHECK_MIN_CROP_SIDE = 48

# The detector can be confident about a region that contains no object at all.
# Measured on this artifact: a uniformly coloured image produced ``glass`` at
# 0.83 and ``paper`` at 0.29, while genuine waste crops from the repository's own
# test images had grayscale standard deviations of 39 to 72. A featureless region
# is therefore an honest reason to ask a human, and it catches a false positive
# that no score threshold would.
FEATURELESS_CROP_STDDEV_THRESHOLD = 8.0

# Minimum whole-image classifier score before its label is treated as evidence
# that contradicts the detector.
CROSS_CHECK_SCORE_THRESHOLD = 0.45

REVIEW_REASON_LOW_SCORE = "low_detection_score"
REVIEW_REASON_UNSUPPORTED_CLASS = "unsupported_material_class"
REVIEW_REASON_UNSUPPORTED_DESTINATION = "unsupported_destination"
REVIEW_REASON_AMBIGUOUS_MATERIAL = "ambiguous_material_confidence"
REVIEW_REASON_OVERLAPPING_MATERIAL = "overlapping_material_conflict"
REVIEW_REASON_FEATURELESS_CROP = "featureless_crop_region"
REVIEW_REASON_CROSS_CHECK = "cross_check_disagreement"


@dataclass(frozen=True)
class CrossCheckResult:
    """Independent whole-image classifier verdict for one detected crop."""

    model_class: str
    category: str
    score: float
    model_identifier: str


@dataclass(frozen=True)
class BatchItemAnalysis:
    """One detected object, analysed and ready to be persisted as a pending scan."""

    item_id: str
    detected_class: str
    category: str
    score: float
    margin: float | None
    box_pixels: tuple[float, float, float, float]
    box_normalized: tuple[float, float, float, float]
    review_status: str
    review_reasons: tuple[str, ...]
    suggested_destination: str
    attempts_holding_bin: bool
    guidance: str
    detector_identifier: str
    runner_up: tuple[str, float] | None = None
    alternate_labels: tuple[tuple[str, float], ...] = ()
    cross_check: CrossCheckResult | None = None
    metadata: dict = field(default_factory=dict)


def _crop_for(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image | None:
    """Return the crop for a pixel box, or ``None`` when it is too small to use."""
    left, top, right, bottom = (int(round(value)) for value in box)
    left = max(0, min(left, image.width - 1))
    top = max(0, min(top, image.height - 1))
    right = max(left + 1, min(right, image.width))
    bottom = max(top + 1, min(bottom, image.height))
    if right - left < CROSS_CHECK_MIN_CROP_SIDE or bottom - top < CROSS_CHECK_MIN_CROP_SIDE:
        return None
    return image.crop((left, top, right, bottom))


def _grayscale_stddev(crop: Image.Image) -> float:
    """Standard deviation of a crop's luma, used to detect featureless regions."""
    import numpy as np

    luma = np.asarray(crop.convert("L"), dtype=np.float32)
    return float(luma.std())


def make_classifier_cross_check(classifier) -> Callable[[Image.Image], CrossCheckResult | None]:
    """Build a crop cross-check backed by the existing whole-image classifier.

    Returns ``None`` for any crop the classifier cannot express as an
    application category, so a label this path does not understand never turns
    into a fabricated disagreement. Uses only public attributes of the
    classifier, which keeps the factory testable with a stub.
    """

    def cross_check(crop: Image.Image) -> CrossCheckResult | None:
        if not getattr(classifier, "ready", False):
            return None
        prediction = classifier.predict(crop)
        model_class = getattr(prediction, "model_class", None)
        score = getattr(prediction, "match_score", None)
        category = PERSISTED_CATEGORY_BY_MODEL_CLASS.get(model_class) if model_class else None
        if category is None or score is None:
            return None
        return CrossCheckResult(
            model_class=model_class,
            category=category,
            score=float(score),
            model_identifier=getattr(classifier, "model_identifier", "unknown"),
        )

    return cross_check


def analyze_detections(
    image: Image.Image,
    detections: Sequence,
    *,
    detector_identifier: str,
    cross_check: Callable[[Image.Image], CrossCheckResult | None] | None = None,
    review_score_threshold: float = REVIEW_SCORE_THRESHOLD,
) -> list[BatchItemAnalysis]:
    """Analyse every detection into a reviewable item.

    ``detections`` are :class:`backend.app.vision_detector.Detection` instances,
    or any object exposing the same ``class_name``, ``score``, ``box``,
    ``runner_up``, ``margin`` and ``alternate_labels`` attributes. Accepting a
    duck-typed sequence is what lets the decision logic be tested without the
    model artifact present.

    Item ids are positional and stable within a single batch response
    (``item-01``, ``item-02``, ...) so the client can reference one item
    unambiguously while it is being reviewed.
    """
    width, height = image.size
    analyses: list[BatchItemAnalysis] = []

    for index, detection in enumerate(detections, start=1):
        detected_class = str(detection.class_name)
        category = DETECTOR_CLASS_TO_APP_CATEGORY.get(detected_class, "holding")
        score = float(detection.score)
        runner_up = getattr(detection, "runner_up", None)
        margin = getattr(detection, "margin", None)
        alternate_labels = tuple(getattr(detection, "alternate_labels", ()) or ())
        box = tuple(float(value) for value in detection.box)

        reasons: list[str] = []
        if score < review_score_threshold:
            reasons.append(REVIEW_REASON_LOW_SCORE)

        if detected_class not in CLASS_POLICIES:
            reasons.append(REVIEW_REASON_UNSUPPORTED_CLASS)

        destination = resolve_destination(category)
        attempts_holding_bin = destination == HOLDING_BIN_ID
        if attempts_holding_bin and REVIEW_REASON_UNSUPPORTED_CLASS not in reasons:
            reasons.append(REVIEW_REASON_UNSUPPORTED_DESTINATION)

        # Reuse the application's registry of visually confusable materials: a
        # narrow gap between two confusable labels is a real ambiguity signal.
        if (
            runner_up is not None
            and margin is not None
            and margin < MARGIN_THRESHOLD
            and is_confusable_pair(
                category, DETECTOR_CLASS_TO_APP_CATEGORY.get(runner_up[0], "holding")
            )
        ):
            reasons.append(REVIEW_REASON_AMBIGUOUS_MATERIAL)

        # The detector returned more than one material label for the same
        # physical region. Those labels are not a registered confusable pair (for
        # example metal against glass), so the pair rule above cannot see them,
        # yet one region cannot honestly be two materials at once.
        if any(
            DETECTOR_CLASS_TO_APP_CATEGORY.get(alternate_name, "holding") != category
            for alternate_name, _ in alternate_labels
        ):
            reasons.append(REVIEW_REASON_OVERLAPPING_MATERIAL)

        metadata: dict = {
            "detector_identifier": detector_identifier,
            "detector_class": detected_class,
            "detector_score": round(score, 6),
            "detector_margin": None if margin is None else round(float(margin), 6),
            "detector_runner_up": None
            if runner_up is None
            else {"class": runner_up[0], "score": round(float(runner_up[1]), 6)},
            "collapsed_alternate_labels": [
                {"class": name, "score": round(float(value), 6)} for name, value in alternate_labels
            ],
        }

        crop = _crop_for(image, box)
        if crop is not None:
            try:
                spread = _grayscale_stddev(crop)
                metadata["crop_grayscale_stddev"] = round(spread, 3)
                metadata["crop_size"] = [crop.width, crop.height]
                if spread < FEATURELESS_CROP_STDDEV_THRESHOLD:
                    reasons.append(REVIEW_REASON_FEATURELESS_CROP)
            except Exception as exc:  # noqa: BLE001 - analysis must not fail the batch
                logger.warning("Crop texture analysis failed (%s)", type(exc).__name__)
                metadata["crop_texture"] = "error"

        cross_check_result: CrossCheckResult | None = None
        if cross_check is not None:
            if crop is None:
                metadata["cross_check"] = "skipped_crop_too_small"
            else:
                try:
                    cross_check_result = cross_check(crop)
                except Exception as exc:  # noqa: BLE001 - a failed cross-check must not fail the batch
                    logger.warning("Crop cross-check failed (%s)", type(exc).__name__)
                    cross_check_result = None
                    metadata["cross_check"] = "error"
                if cross_check_result is None:
                    metadata.setdefault("cross_check", "no_result")
                else:
                    metadata["cross_check"] = "completed"
                    metadata["cross_check_model_class"] = cross_check_result.model_class
                    metadata["cross_check_category"] = cross_check_result.category
                    metadata["cross_check_score"] = round(float(cross_check_result.score), 6)
                    metadata["cross_check_model_identifier"] = cross_check_result.model_identifier
                    if (
                        cross_check_result.score >= CROSS_CHECK_SCORE_THRESHOLD
                        and cross_check_result.category != category
                    ):
                        reasons.append(REVIEW_REASON_CROSS_CHECK)

        guidance = (
            CLASS_POLICIES[detected_class][2]
            if detected_class in CLASS_POLICIES
            else UNSUPPORTED_CLASS_GUIDANCE
        )

        analyses.append(
            BatchItemAnalysis(
                item_id=f"item-{index:02d}",
                detected_class=detected_class,
                category=category,
                score=score,
                margin=None if margin is None else float(margin),
                box_pixels=box,
                box_normalized=(
                    round(box[0] / width, 6),
                    round(box[1] / height, 6),
                    round(box[2] / width, 6),
                    round(box[3] / height, 6),
                ),
                review_status="needs_review" if reasons else "ready",
                review_reasons=tuple(reasons),
                suggested_destination=destination,
                attempts_holding_bin=attempts_holding_bin,
                guidance=guidance,
                detector_identifier=detector_identifier,
                runner_up=runner_up,
                alternate_labels=alternate_labels,
                cross_check=cross_check_result,
                metadata=metadata,
            )
        )

    return analyses
