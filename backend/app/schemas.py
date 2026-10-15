"""Stable, model-independent response contract for image scans."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


MaterialCategory = Literal["recyclable", "reusable", "biodegradable", "hazardous"]
ClassificationStatus = Literal["success", "uncertain"]


class ClassificationResponse(BaseModel):
    """A transient vision result; it does not imply durable scan storage.

    ``match_score`` is optional and, when present, is a model-supported
    comparison score in [0, 1]. It is not a calibrated probability.
    ``predicted_item`` and ``predicted_category`` are null when the model does
    not clear the documented uncertainty thresholds.
    """

    model_config = ConfigDict(extra="forbid")

    scan_id: UUID = Field(description="Unique ID for this request; not a persistence record ID.")
    predicted_item: str | None = Field(default=None, description="Best-supported item description, or null when uncertain.")
    predicted_category: MaterialCategory | None = Field(default=None, description="Application category, or null when uncertain.")
    match_score: float | None = Field(default=None, ge=0.0, le=1.0, description="Candidate comparison score; not a calibrated probability.")
    manual_review_recommended: bool
    suggested_route: str = Field(min_length=1, description="Conditional handling guidance, not a local-facility acceptance decision.")
    explanation: str = Field(min_length=1, description="Concise reasoning and material limitations.")
    model_identifier: str = Field(min_length=1, description="Configured model/checkpoint identifier.")
    classification_status: ClassificationStatus
