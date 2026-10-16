"""Stable, model-independent response contract for image scans."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


MaterialCategory = Literal["recyclable", "reusable", "biodegradable", "hazardous"]
ClassificationStatus = Literal["success", "uncertain"]
BatchReviewStatus = Literal["ready", "needs_review"]


class ClassificationResponse(BaseModel):
    """A vision result whose scan record is committed before the response.

    ``scan_id`` is the primary key of the persisted ``Scan`` record. Creating
    that pending scan does not add confirmed inventory; inventory changes only
    after a separate user confirmation.

    ``match_score`` is optional and, when present, is a model-supported
    comparison score in [0, 1]. It is not a calibrated probability.
    ``predicted_item`` and ``predicted_category`` are null when the model does
    not clear the documented uncertainty thresholds.
    """

    model_config = ConfigDict(extra="forbid")

    scan_id: UUID = Field(description="Primary key of the persisted Scan record created by this request.")
    predicted_item: str | None = Field(default=None, description="Best-supported item description, or null when uncertain.")
    predicted_category: MaterialCategory | None = Field(default=None, description="Application category, or null when uncertain.")
    match_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Candidate comparison score; not a calibrated probability.")
    manual_review_recommended: bool
    suggested_route: str = Field(min_length=1, description="Conditional handling guidance, not a local-facility acceptance decision.")
    explanation: str = Field(min_length=1, description="Concise reasoning and material limitations.")
    model_identifier: str = Field(min_length=1, description="Configured model/checkpoint identifier.")
    classification_status: ClassificationStatus


# ---------------------------------------------------------------------------
# Mixed-waste batch scanning
#
# Each item in a batch is a real detector finding with its own persisted pending
# scan. Creating a batch never changes inventory; inventory moves only when an
# item is separately confirmed. Review status is ``needs_review`` when any
# documented reason applies, and those reasons are always returned so the client
# can explain itself rather than guessing.
# ---------------------------------------------------------------------------


class DetectionBox(BaseModel):
    """One bounding box in both pixel and normalized image coordinates.

    Both forms are returned because they serve different consumers: pixels for
    drawing on a fixed-size bitmap, normalized fractions for layout that scales
    with the rendered image. Returning only one invites the client to derive the
    other, which is where box misalignment bugs come from.
    """

    model_config = ConfigDict(extra="forbid")

    x1: float = Field(description="Left edge in pixels of the scanned image.")
    y1: float = Field(description="Top edge in pixels of the scanned image.")
    x2: float = Field(description="Right edge in pixels of the scanned image.")
    y2: float = Field(description="Bottom edge in pixels of the scanned image.")
    normalized_x1: float = Field(ge=0.0, le=1.0, description="Left edge as a fraction of image width.")
    normalized_y1: float = Field(ge=0.0, le=1.0, description="Top edge as a fraction of image height.")
    normalized_x2: float = Field(ge=0.0, le=1.0, description="Right edge as a fraction of image width.")
    normalized_y2: float = Field(ge=0.0, le=1.0, description="Bottom edge as a fraction of image height.")


class CropCrossCheck(BaseModel):
    """Independent whole-image classifier verdict for this item's crop.

    Present only when the cross-check actually ran. It is corroborating
    evidence, not the primary label, and its score is a model comparison score
    rather than a calibrated probability.
    """

    model_config = ConfigDict(extra="forbid")

    model_class: str = Field(min_length=1)
    category: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    model_identifier: str = Field(min_length=1)


class BatchScanItem(BaseModel):
    """One detected object within a mixed-waste scene."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(description="Stable identifier of this item within its batch response.")
    scan_id: UUID = Field(
        description="Persisted pending scan for this item; confirm it to record inventory."
    )
    detected_class: str = Field(description="Material class reported by the object detector.")
    category: str = Field(description="Application category this item would be routed as.")
    score: float = Field(ge=0.0, le=1.0, description="Detector score; not a calibrated probability.")
    margin: float | None = Field(
        default=None, description="Gap to the strongest competing material label, when known."
    )
    box: DetectionBox
    review_status: BatchReviewStatus
    review_reasons: list[str] = Field(
        description="Documented reasons this item needs review; empty when review_status is 'ready'."
    )
    suggested_destination: str = Field(description="Virtual bin this item would be routed to.")
    attempts_holding_bin: bool = Field(
        description="True when routing cannot place this item in a material bin."
    )
    guidance: str = Field(min_length=1, description="Conditional handling guidance.")
    cross_check: CropCrossCheck | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Detection and classification metadata for debugging."
    )


class BatchScanResponse(BaseModel):
    """Result of scanning one image that may contain several waste items.

    An empty ``items`` list is a real outcome: the detector found nothing it
    trusts. It is never replaced with a fabricated detection derived from a
    single whole-image label.
    """

    model_config = ConfigDict(extra="forbid")

    batch_id: UUID = Field(description="Persisted batch record grouping this scene's detected items.")
    image_width: int = Field(gt=0)
    image_height: int = Field(gt=0)
    detection_count: int = Field(ge=0)
    review_required_count: int = Field(ge=0)
    detector_identifier: str = Field(min_length=1)
    detector_license: str = Field(min_length=1, description="Licence declared by the detector artifact.")
    detector_diagnostic_status: str = Field(min_length=1)
    items: list[BatchScanItem]
    notes: list[str] = Field(
        default_factory=list, description="Honest statements about what this result does and does not mean."
    )


class DetectorStatusResponse(BaseModel):
    """Readiness and provenance of the mixed-waste object detector."""

    model_config = ConfigDict(extra="forbid")

    initialized_successfully: bool
    inference_available: bool
    diagnostic_status: str
    detector_identifier: str
    detector_source: str
    detector_license: str
    detector_architecture: str
    detector_class_names: list[str]
    detection_score_threshold: float
    nms_iou_threshold: float
    same_object_iou_threshold: float
    notes: list[str]
