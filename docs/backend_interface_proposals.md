# Backend Interface Proposals & Integration Contracts (Round 2)
**Role:** Backend Data & Application Services Engineer  
**Status:** Round 2 Finalized Contracts & Verified Hand-off Specifications  
**Target Audience:** Backend Lead, Frontend Lead, System Integrators  

---

## 1. Proposals Awaiting Other Owners (Action Items)

### 1.1 `backend/app/main.py`: Add CORSMiddleware (Owner: Backend Lead)
**Blocker:** In-browser fetches from the Next.js frontend (`http://localhost:3000`) to the FastAPI backend (`http://localhost:8000`) are blocked by browser CORS security policies.

**Exact Proposed Diff:**
```python
# In backend/app/main.py
from fastapi.middleware.cors import CORSMiddleware

# Immediately after: app = FastAPI(...)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 1.2 `backend/requirements.txt`: Add Alembic (Owner: Backend Lead)
**Issue:** `backend/alembic.ini` and `backend/alembic/` exist in the repository, but `alembic` is omitted from `backend/requirements.txt`. Clean environment setups cannot run explicit migrations without manual installation.

**Exact Proposed Line:**
```text
alembic>=1.13.0
```

### 1.3 WebSocket Path Reconciliation (Owner: Backend Lead & Frontend Team)
**Issue:** The backend serves WebSocket connections at `/ws` ([backend/app/main.py:L99](file:///backend/app/main.py#L99)), but `frontend/src/features/dashboard/INTEGRATION.md` specifies `ws://<HOST>:8000/api/live`.

**Recommended Resolution:**
1. Frontend should connect to `NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws` (already documented in `frontend/.env.example`).
2. Alternatively, backend lead can add an alias route in `backend/app/main.py`:
```python
# In backend/app/main.py (Alias for /ws)
@app.websocket("/api/live")
async def live_websocket_alias(websocket: WebSocket) -> None:
    await websocket_endpoint(websocket)
```

### 1.4 Dashboard Branch Integration (Owner: Frontend Lead & Nikki)
**Issue:** Dashboard components (`DashboardView.tsx`, `VirtualBinGrid.tsx`, `MaterialFlow.tsx`, `RecentEvents.tsx`) were developed on isolated branch `origin/feat/digital-twin-dashboard` and are not yet merged into `feat/full-app-integration`. In `frontend/src/app/page.tsx`, only the mobile camera scanner is rendered.
**Action:** Merge `origin/feat/digital-twin-dashboard` into `feat/full-app-integration` and mount `DashboardView` via a header navigation tab or `/dashboard` route.

### 1.5 Proposed Request-ID Correlation Middleware for `main.py` (Owner: Backend Lead)
To achieve end-to-end request tracing across all endpoints:
```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from backend.app.adapters.request_context import sanitize_message

class RequestIdLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = req_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

app.add_middleware(RequestIdLoggingMiddleware)
```

---

## 2. Final Backend Response Shapes (Round 2 Verified)

### 2.1 `GET /api/twin/snapshot`
Real-time ground-truth state computed strictly from persisted records. Includes both standard and dashboard presentation aliases:
```json
{
  "timestamp": "2026-10-15T17:41:31.821399Z",
  "total_confirmed_items": 1.0,
  "total_items_processed": 1.0,
  "active_routes": 1,
  "category_inventory": {
    "glass": 0.0,
    "holding": 0.0,
    "metal": 0.0,
    "organic": 0.0,
    "paper": 0.0,
    "plastic": 1.0
  },
  "bins": [
    {
      "id": "bin-plastic",
      "name": "Plastic Recycling",
      "accepted_category": "plastic",
      "current_inventory": 1.0,
      "capacity": 100.0,
      "inventory_unit": "items",
      "occupancy_percentage": 1.0,
      "status": "normal",
      "contamination_risk": 0.0,
      "last_updated": "2026-10-15T17:41:53.913055Z",
      "needs_service": false
    }
  ],
  "processing_totals": {},
  "pending_verification_count": 0
}
```

### 2.2 `GET /api/twin/history?limit=50`
Read-only historical snapshot records captured synchronously upon committed inventory mutations:
```json
[
  {
    "id": "3b2903fe-e0d0-4bf6-b565-df4d9d15ad09",
    "timestamp": "2026-10-15T17:41:53.913500Z",
    "total_items": 1.0,
    "bin_states": {
      "bin-plastic": {
        "name": "Plastic Recycling",
        "category": "plastic",
        "current_inventory": 1.0,
        "capacity": 100.0,
        "occupancy_percentage": 1.0,
        "status": "normal"
      }
    },
    "is_demo": false
  }
]
```

### 2.3 `GET /api/events`
Audit history with filtering, cursor pagination, and **reconnect event replay**:
- Query parameter `last_event_id` or `since_id`: Replays all events committed *after* the specified event in chronological order.
- Returns both `items` and alias `events` for universal frontend compatibility.
```json
{
  "items": [
    {
      "id": "680ebcfd-85fc-4625-b243-99e5c71ac42c",
      "event_type": "confirmed",
      "material_id": "46305cf9-d87f-4723-9301-84dcf076a073",
      "scan_id": "8e03d4f0-d92c-4421-9f6f-4e4554d97716",
      "source_bin_id": null,
      "destination_bin_id": "bin-plastic",
      "quantity": 1.0,
      "unit": "items",
      "affected_category": "plastic",
      "payload": {
        "uncertainty_reason": null,
        "is_ambiguous": false,
        "description": "Confirmed plastic",
        "verification_answers": null
      },
      "idempotency_key": "user-client-uuid",
      "is_demo": false,
      "timestamp": "2026-10-15T17:41:53.913590Z"
    }
  ],
  "events": [...],
  "next_cursor": null,
  "total_count": 1
}
```

### 2.4 `POST /api/materials/confirm` (HTTP 201)
Atomic confirmation and routing with conditional capacity update to guard against concurrent overflow:
```json
{
  "id": "46305cf9-d87f-4723-9301-84dcf076a073",
  "scan_id": "8e03d4f0-d92c-4421-9f6f-4e4554d97716",
  "description": "Confirmed plastic",
  "category": "plastic",
  "confirmed_category": "plastic",
  "predicted_category": "plastic",
  "quantity": 1.0,
  "unit": "items",
  "destination": "bin-plastic",
  "processing_status": "confirmed",
  "confirmation_source": "user_corrected",
  "confidence_at_confirmation": 0.92,
  "verification_answers": null,
  "is_demo": false,
  "created_at": "2026-10-15T17:41:53.913055Z",
  "updated_at": "2026-10-15T17:41:53.913056Z"
}
```

### 2.5 `GET /api/recommendations` & `POST /api/recommendations/generate`
Provides both data-twin fields and dashboard presentation fields:
```json
{
  "id": "ace8bbaf-cfaf-4537-b60d-1a205005cb66",
  "title": "System Status Normal: Stable Flow Distribution",
  "recommendation_text": "All virtual bins are operating within normal simulation capacity thresholds.",
  "description": "All virtual bins are operating within normal simulation capacity thresholds.",
  "action_type": "sorting_action",
  "severity": "medium",
  "generation_method": "deterministic_fallback",
  "supporting_data": {
    "trigger": "normal_operations",
    "bin_ids": ["bin-glass", "bin-holding", "bin-metal", "bin-organic", "bin-paper", "bin-plastic"],
    "event_ids": []
  },
  "status": "new",
  "is_demo": false,
  "created_at": "2026-10-15T17:41:47.393852Z",
  "updated_at": "2026-10-15T17:41:47.393854Z"
}
```

---

## 3. WebSocket Broadcast Protocol (`/ws`)

When a client connects to `ws://<HOST>:8000/ws`, the server immediately sends an initial full state snapshot envelope, followed by real-time post-commit event envelopes:

### 3.1 Initial Connection Envelope
```json
{
  "type": "snapshot",
  "data": {
    "timestamp": "2026-10-15T17:41:31.821399Z",
    "total_confirmed_items": 1.0,
    "bins": [...],
    "category_inventory": {...}
  }
}
```

### 3.2 Real-time Mutation Event Envelopes
Emitted strictly AFTER successful database commit:
- `material_confirmed`:
  ```json
  {
    "type": "material_confirmed",
    "data": {
      "material_id": "46305cf9-...",
      "scan_id": "8e03d4f0-...",
      "category": "plastic",
      "destination_bin_id": "bin-plastic",
      "quantity": 1.0,
      "status": "confirmed",
      "bin_inventory": 1.0,
      "bin_capacity": 100.0
    }
  }
  ```
- `material_reclassified`:
  ```json
  {
    "type": "material_reclassified",
    "data": {
      "material_id": "uuid",
      "source_bin_id": "bin-holding",
      "destination_bin_id": "bin-plastic",
      "new_category": "plastic",
      "quantity": 1.0
    }
  }
  ```
- `bin_emptied`:
  ```json
  {
    "type": "bin_emptied",
    "data": {
      "bin_id": "bin-plastic",
      "cleared_quantity": 45.0
    }
  }
  ```
- `bin_transferred`:
  ```json
  {
    "type": "bin_transferred",
    "data": {
      "from_bin_id": "bin-plastic",
      "to_bin_id": "bin-holding",
      "quantity": 10.0
    }
  }
  ```
- `event_reversed`:
  ```json
  {
    "type": "event_reversed",
    "data": {
      "reversed_event_id": "evt-uuid-1",
      "reversal_event_id": "evt-uuid-2"
    }
  }
  ```

---

## 4. Proposed Root README Quick-Start Section

```markdown
## Quick-Start Development Guide (2 Terminals)

### Terminal 1: Backend API (FastAPI)
```bash
# Set up Python virtual environment
python3 -m venv backend/.venv
source backend/.venv/bin/activate  # On Windows: backend\.venv\Scripts\activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env

# Run server on port 8000
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Interactive Swagger docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Terminal 2: Frontend Web App (Next.js)
```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```
Web Application: [http://localhost:3000](http://localhost:3000)
```
