"""
Pydantic API Schema Adapter.
Provides schemas required for Data, Twin, Events, and Recommendations.
Checks backend.app.schemas first to adopt any schemas defined by the backend lead.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# Try importing from lead's schemas if defined
try:
    import backend.app.schemas as lead_schemas
except ImportError:
    lead_schemas = None


def _get_or_default(schema_name: str, fallback_cls):
    if lead_schemas and hasattr(lead_schemas, schema_name):
        return getattr(lead_schemas, schema_name)
    return fallback_cls


# ----------------- SCAN SCHEMAS -----------------

class _DefaultScanCreate(BaseModel):
    image_url: Optional[str] = None
    predicted_category: str
    confidence: float
    model_identifier: str = "yolov8-recycling-v1"
    top_k_predictions: Optional[List[Dict[str, Any]]] = None
    margin: Optional[float] = None
    ocr_cues: Optional[List[str]] = None
    is_demo: bool = False

ScanCreate = _get_or_default("ScanCreate", _DefaultScanCreate)


class _DefaultScanResponse(BaseModel):
    id: str
    image_url: Optional[str] = None
    predicted_category: str
    confidence: float
    model_identifier: str
    review_status: str
    top_k_predictions: Optional[List[Dict[str, Any]]] = None
    margin: Optional[float] = None
    ocr_cues: Optional[List[str]] = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

ScanResponse = _get_or_default("ScanResponse", _DefaultScanResponse)


# ----------------- MATERIAL SCHEMAS -----------------

class _DefaultMaterialConfirmRequest(BaseModel):
    scan_id: str
    confirmed_category: str
    quantity: float = Field(default=1.0, ge=0)
    unit: str = Field(default="items")
    destination_bin_id: Optional[str] = None
    confirmation_source: str = Field(default="model_accepted")
    description: Optional[str] = None
    verification_answers: Optional[Dict[str, Any]] = None
    idempotency_key: Optional[str] = None

MaterialConfirmRequest = _get_or_default("MaterialConfirmRequest", _DefaultMaterialConfirmRequest)


class _DefaultMaterialEntryResponse(BaseModel):
    id: str
    scan_id: Optional[str] = None
    description: Optional[str] = None
    category: str
    confirmed_category: str
    predicted_category: Optional[str] = None
    quantity: float
    unit: str
    destination: str
    processing_status: str
    confirmation_source: str
    confidence_at_confirmation: Optional[float] = None
    verification_answers: Optional[Dict[str, Any]] = None
    is_demo: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

MaterialEntryResponse = _get_or_default("MaterialEntryResponse", _DefaultMaterialEntryResponse)


class _DefaultReclassifyRequest(BaseModel):
    target_category: str
    target_bin_id: Optional[str] = None
    verification_answers: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    idempotency_key: Optional[str] = None

ReclassifyRequest = _get_or_default("ReclassifyRequest", _DefaultReclassifyRequest)


# ----------------- BIN SCHEMAS -----------------

class _DefaultBinCreateRequest(BaseModel):
    id: str
    name: str
    accepted_category: str
    capacity: float = Field(gt=0)
    inventory_unit: str = "items"

BinCreateRequest = _get_or_default("BinCreateRequest", _DefaultBinCreateRequest)


class _DefaultBinUpdateRequest(BaseModel):
    name: Optional[str] = None
    capacity: Optional[float] = Field(default=None, gt=0)
    status: Optional[str] = None

BinUpdateRequest = _get_or_default("BinUpdateRequest", _DefaultBinUpdateRequest)


class _DefaultBinSnapshot(BaseModel):
    id: str
    name: str
    accepted_category: str
    current_inventory: float
    capacity: float
    inventory_unit: str
    occupancy_percentage: Optional[float] = None
    status: str
    contamination_risk: float = 0.0

    model_config = ConfigDict(from_attributes=True)

BinSnapshot = _get_or_default("BinSnapshot", _DefaultBinSnapshot)
BinResponse = BinSnapshot


class _DefaultBinTransferRequest(BaseModel):
    from_bin_id: str
    to_bin_id: str
    quantity: float = Field(gt=0)
    reason: Optional[str] = None

BinTransferRequest = _get_or_default("BinTransferRequest", _DefaultBinTransferRequest)


# ----------------- TWIN SCHEMAS -----------------

class _DefaultDigitalTwinSnapshot(BaseModel):
    timestamp: datetime
    total_confirmed_items: float
    category_inventory: Dict[str, float]
    bins: List[BinSnapshot]
    processing_totals: Dict[str, float]
    pending_verification_count: int

DigitalTwinSnapshot = _get_or_default("DigitalTwinSnapshot", _DefaultDigitalTwinSnapshot)


class _DefaultSimulationItem(BaseModel):
    category: str
    quantity: float = Field(gt=0)
    destination_bin_id: Optional[str] = None


class _DefaultSimulationRequest(BaseModel):
    hypothetical_additions: List[_DefaultSimulationItem]
    hypothetical_misclassification_rates: Optional[Dict[str, float]] = None  # e.g. {"bin-plastic": 0.15}

SimulationRequest = _get_or_default("SimulationRequest", _DefaultSimulationRequest)


class _DefaultSimulatedBinEffect(BaseModel):
    bin_id: str
    bin_name: str
    starting_inventory: float
    projected_inventory: float
    capacity: float
    projected_occupancy_percentage: Optional[float]
    projected_status: str
    would_overflow: bool
    potential_contamination_items: float

SimulatedBinEffect = _get_or_default("SimulatedBinEffect", _DefaultSimulatedBinEffect)


class _DefaultSimulationResponse(BaseModel):
    simulation_label: str = "HYPOTHETICAL_SIMULATION_READ_ONLY"
    timestamp: datetime
    bin_projections: List[SimulatedBinEffect]
    summary_notes: List[str]

SimulationResponse = _get_or_default("SimulationResponse", _DefaultSimulationResponse)


# ----------------- EVENT SCHEMAS -----------------

class _DefaultMaterialEventResponse(BaseModel):
    id: str
    event_type: str
    material_id: Optional[str] = None
    scan_id: Optional[str] = None
    source_bin_id: Optional[str] = None
    destination_bin_id: Optional[str] = None
    quantity: float
    unit: str
    affected_category: str
    payload: Optional[Dict[str, Any]] = None
    idempotency_key: Optional[str] = None
    is_demo: bool
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

MaterialEventResponse = _get_or_default("MaterialEventResponse", _DefaultMaterialEventResponse)


class _DefaultEventListResponse(BaseModel):
    items: List[MaterialEventResponse]
    next_cursor: Optional[str] = None
    total_count: int

EventListResponse = _get_or_default("EventListResponse", _DefaultEventListResponse)


class _DefaultEventReversalRequest(BaseModel):
    event_id: Optional[str] = None
    reason: Optional[str] = None

EventReversalRequest = _get_or_default("EventReversalRequest", _DefaultEventReversalRequest)


# ----------------- RECOMMENDATION SCHEMAS -----------------

class _DefaultRecommendationResponse(BaseModel):
    id: str
    title: str
    recommendation_text: str
    generation_method: str  # llm | deterministic_fallback
    supporting_data: Dict[str, Any]
    status: str
    is_demo: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

RecommendationResponse = _get_or_default("RecommendationResponse", _DefaultRecommendationResponse)


class _DefaultRecommendationGenerateRequest(BaseModel):
    force_refresh: bool = False


class _DefaultRecommendationStatusUpdate(BaseModel):
    status: str = Field(description="One of 'new', 'acknowledged', 'dismissed', 'resolved'")


class _DefaultRecommendationAskRequest(BaseModel):
    question: str


class _DefaultRecommendationAskResponse(BaseModel):
    question: str
    answer: str
    generation_method: str
    supporting_context: Dict[str, Any]
    timestamp: datetime

RecommendationAskResponse = _get_or_default("RecommendationAskResponse", _DefaultRecommendationAskResponse)


# ----------------- ANALYTICS SCHEMAS -----------------

class _DefaultCorrectionRateItem(BaseModel):
    category: str
    total_scanned: int
    corrected_count: int
    correction_rate: float

CorrectionRateItem = _get_or_default("CorrectionRateItem", _DefaultCorrectionRateItem)


class _DefaultCorrectionRateResponse(BaseModel):
    category_rates: List[CorrectionRateItem]
    overall_correction_rate: float
    total_confirmed_scans: int

CorrectionRateResponse = _get_or_default("CorrectionRateResponse", _DefaultCorrectionRateResponse)


class _DefaultConfusionMatrixResponse(BaseModel):
    categories: List[str]
    matrix: Dict[str, Dict[str, int]]  # predicted -> confirmed -> count
    high_risk_confusions: List[Dict[str, Any]]

ConfusionMatrixResponse = _get_or_default("ConfusionMatrixResponse", _DefaultConfusionMatrixResponse)
