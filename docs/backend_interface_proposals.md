# Backend Interface Proposals & Integration Contracts
**Role:** Backend Data & Application Services Engineer
**Target Audience:** Backend Lead (Vision & API Integration)
**Status:** Working Proposal / Non-competing Adapter Pattern

This document establishes the proposed contracts and interfaces for shared components between the Computer Vision / Scan API and the Data Persistence / Digital Twin / Recommendation services.

---

## 1. Shared Dependency Manifest (`backend/requirements.txt`)
Proposed production dependencies for coordination with the backend lead:
```text
fastapi>=0.110.0
uvicorn>=0.28.0
sqlalchemy>=2.0.0
pydantic>=2.6.0
python-multipart>=0.0.9
alembic>=1.13.0
httpx>=0.27.0
pytest>=8.0.0
```

---

## 2. Scan Entity & Vision Contract
Proposed extension to the `Scan` model and scan endpoint payload:
```python
# Scan metadata produced by Vision inference
{
    "id": "uuid-str",
    "image_url": "optional/path/to/image.jpg",
    "predicted_category": "plastic",  # Primary class
    "confidence": 0.88,               # Top-1 confidence [0.0 - 1.0]
    "model_identifier": "yolov8-recycling-v1",
    "review_status": "pending",       # 'pending' | 'needs_review' | 'confirmed' | 'rejected'

    # Extended uncertainty fields:
    "top_k_predictions": [            # Top candidate classes with probabilities
        {"category": "plastic", "score": 0.52},
        {"category": "paper", "score": 0.48}
    ],
    "margin": 0.04,                   # Score difference between top-1 and top-2
    "ocr_cues": ["recyclable", "PETE 1"], # Optional text detected on packaging
    "created_at": "ISO-8601-timestamp"
}
```
**Uncertainty rule:**
If `confidence < 0.70` or `margin < 0.15` between a confusable pair (e.g. `paper` vs `plastic`, `compostable` vs `plastic`), `review_status` is automatically set to `needs_review` and routing defaults to the "Needs Verification" holding bin.

---

## 3. Shared Pydantic API Schemas (`backend/app/schemas.py`)
To avoid competing schemas while `backend/app/schemas.py` is initialized, our services import from `backend.app.adapters.schemas`, which transparently falls back to our proposed definitions until the lead populates `schemas.py`.

### 3.1 Material Confirmation Schema
```python
class MaterialConfirmRequest(BaseModel):
    scan_id: str
    confirmed_category: str
    quantity: float = Field(gt=0, default=1.0)
    unit: str = Field(default="items")  # 'items', 'kg', 'g', 'l', 'units'
    destination_bin_id: Optional[str] = None # If omitted, resolved via routing rules
    confirmation_source: str = "model_accepted" # 'model_accepted' | 'user_visual' | 'user_label_check' | 'manual_override'
    description: Optional[str] = None
    verification_answers: Optional[dict] = None # E.g. resin code, lining check

class MaterialEntryResponse(BaseModel):
    id: str
    scan_id: Optional[str]
    description: Optional[str]
    category: str
    confirmed_category: str
    predicted_category: Optional[str]
    quantity: float
    unit: str
    destination: str
    processing_status: str
    confirmation_source: str
    confidence_at_confirmation: Optional[float]
    created_at: datetime
```

### 3.2 Digital Twin Snapshot Schema
```python
class BinSnapshot(BaseModel):
    id: str
    name: str
    accepted_category: str
    current_inventory: float
    capacity: float
    inventory_unit: str
    occupancy_percentage: Optional[float]
    status: str # 'normal' | 'warning' | 'full' | 'maintenance'
    contamination_risk: float # [0.0 - 1.0] simulation indicator

class DigitalTwinSnapshot(BaseModel):
    timestamp: datetime
    total_confirmed_items: float
    category_inventory: dict[str, float]
    bins: list[BinSnapshot]
    processing_totals: dict[str, float]
    pending_verification_count: int
```

### 3.3 Event Schema
```python
class MaterialEventResponse(BaseModel):
    id: str
    event_type: str # 'confirmed' | 'routed' | 'reclassified' | 'emptied' | 'transferred' | 'processed' | 'reversal'
    material_id: Optional[str]
    scan_id: Optional[str]
    source_bin_id: Optional[str]
    destination_bin_id: Optional[str]
    quantity: float
    unit: str
    affected_category: str
    payload: Optional[dict]
    timestamp: datetime
```

### 3.4 Recommendation Schemas
```python
class RecommendationResponse(BaseModel):
    id: str
    title: str
    recommendation_text: str
    generation_method: str # 'llm' | 'deterministic_fallback'
    supporting_data: dict
    status: str # 'new' | 'acknowledged' | 'dismissed' | 'resolved'
    created_at: datetime
```

---

## 4. WebSocket Event Publishing Interface
Proposed interface in `backend/app/adapters/event_publisher.py`:
```python
def publish_event(event_type: str, payload: dict) -> None:
    """
    Called strictly AFTER database transaction commit.
    Invokes registered listeners (such as WebSocket manager broadcast).
    Does not crash or raise on client broadcast errors.
    """
```
**Lead Integration Hook:**
In `backend/app/main.py`:
```python
from backend.app.adapters.event_publisher import register_event_listener

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    # ...

# Wire publisher to WebSocket manager:
register_event_listener(lambda event_type, data: asyncio.create_task(manager.broadcast({"type": event_type, "data": data})))
```

---

## 5. Router Mounting for `backend/app/main.py`
Each router currently declares its complete `/api/...` prefix in its own
`APIRouter`. Mount it without another prefix to avoid duplicate paths:
```python
from backend.app.routers import materials, twin, events, recommendations, bins, analytics

app.include_router(materials.router)
app.include_router(twin.router)
app.include_router(events.router)
app.include_router(recommendations.router)
app.include_router(bins.router)
app.include_router(analytics.router)
```

The integrated vision scan persists a material-specific predicted category and
model score on `Scan`. The response continues to expose the vision API's broad
application category (`recyclable`, `biodegradable`, or `hazardous`). The model
class and top scores are preserved in `top_k_predictions`; class mappings for
persistence are battery → hazardous, biological → organic, cardboard → paper,
and trash → holding, while glass, metal, paper, and plastic retain their
material categories. Uncertain items use `review_status="needs_review"`.
The current Digital Twin has no dedicated hazardous or reusable bin, so those
confirmed categories route to the existing `bin-holding` pending a supported
destination.
