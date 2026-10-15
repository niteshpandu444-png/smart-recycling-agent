# Smart Recycling Agent — Shared API Contract

**Version:** 1.0.0  
**Status:** Canonical Reference  
**Roles Involved:** Frontend Lead (Mobile Scanner), Dashboard Developer (Digital Twin), Backend Developer (FastAPI)

---

## 1. Overview & Architectural Principles

The **Smart Recycling Agent** integrates:
1. **Computer Vision Inference** for real-time item and material classification.
2. **Digital Twin State Engine** for tracking inventory weights, bin capacities, and circular material routing.
3. **Generative AI Recommendations** grounded in actual Digital Twin state (never fabricated on the client).

### Key Rules
- **Backend as Source of Truth:** The frontend UI must never simulate or increment inventory counts locally before the backend confirms successful database persistence.
- **Model Confidence Scores:** `match_score` values are model-specific confidence metrics (0.0 to 1.0) and must not be treated as absolute statistical probabilities.
- **Idempotency:** Item confirmations use client-generated `idempotency_key` identifiers to prevent double-counting on network retries.
- **CORS Requirements:** The backend must allow origins specified by the frontend (including local LAN IPs for mobile device testing).

---

## 2. Base Configuration & Environments

| Environment | Frontend Origin | Backend Base URL |
| :--- | :--- | :--- |
| **Local Laptop Dev** | `http://localhost:3000` | `http://localhost:8000` |
| **Mobile LAN Testing** | `http://<LAPTOP_LAN_IP>:3000` | `http://<LAPTOP_LAN_IP>:8000` |
| **Live WebSocket** | `ws://<HOST>:8000/api/live` | `ws://<HOST>:8000/api/live` |

> [!IMPORTANT]
> **Mobile Device LAN Rule:** When testing on a physical phone over local Wi-Fi, the phone **cannot** reach `localhost:8000`. You must configure `NEXT_PUBLIC_API_BASE_URL=http://<YOUR_LAPTOP_IP>:8000` in `frontend/.env.local`.

---

## 3. Standard Data Enums

### Recycling Categories (`RecyclingCategory`)
- `recyclable` — Paper, plastics (PET/HDPE), glass, aluminum, metals.
- `reusable` — Functional containers, electronics, repairable goods.
- `biodegradable` — Organic food waste, compostable paper/packaging.
- `hazardous` — Batteries, chemicals, medical waste, toxic electronics.

### Classification Status (`ClassificationStatus`)
- `success` — High confidence; routing suggestion verified.
- `uncertain` — Lower confidence or ambiguous object; manual verification strongly flagged.
- `failed` — Unrecognizable, blurred, or unsupported item.

---

## 4. Error Response Schema

All non-2xx responses should return a consistent JSON schema:

```json
{
  "error": {
    "code": "ITEM_UNCLASSIFIABLE",
    "message": "The uploaded image was too blurry or obstructed to classify.",
    "details": {
      "confidence": 0.21,
      "threshold": 0.60
    }
  }
}
```

Standard HTTP status codes used:
- `200 OK` / `201 Created` — Successful operations.
- `400 Bad Request` — Missing parameters or invalid payloads.
- `404 Not Found` — Requested scan, bin, or resource not found.
- `408 Request Timeout` — Model inference or processing took too long.
- `422 Unprocessable Entity` — Pydantic validation failures.
- `500 Internal Server Error` — Unhandled backend or ML pipeline exceptions.

---

## 5. Endpoints Specification

### 5.1 Classification Endpoint
**`POST /api/scans`**

Submits an image captured via camera or file picker for computer vision classification.

- **Content-Type:** `multipart/form-data`
- **Body:**
  - `file`: Binary image data (`image/jpeg`, `image/png`, `image/webp`).

#### Success Response (`200 OK`)
```json
{
  "scan_id": "scan_8f912c9b4e",
  "predicted_item": "Aluminum Beverage Can",
  "predicted_category": "recyclable",
  "match_score": 0.94,
  "manual_review_recommended": false,
  "suggested_route": "Bin A - Metals & Aluminum",
  "explanation": "Detected clean beverage can with visible metallic texture and recycling logo.",
  "model_identifier": "yolov8-recycling-v2",
  "classification_status": "success",
  "created_at": "2026-10-15T12:00:00Z"
}
```

#### Low Confidence / Uncertain Response (`200 OK`)
```json
{
  "scan_id": "scan_a3b2c1d0",
  "predicted_item": "Composite Drink Carton",
  "predicted_category": "recyclable",
  "match_score": 0.52,
  "manual_review_recommended": true,
  "suggested_route": "Manual Sorting Bin",
  "explanation": "Object contains multi-material layers (foil and paper). Verify local municipal facility capabilities.",
  "model_identifier": "yolov8-recycling-v2",
  "classification_status": "uncertain",
  "created_at": "2026-10-15T12:01:00Z"
}
```

---

### 5.2 Confirmation Endpoint
**`POST /api/scans/{id}/confirm`**

Submits verified or edited classification details to commit the item to the Digital Twin inventory.

- **Headers:**
  - `Content-Type: application/json`
  - `Idempotency-Key: <UUID>`
- **Path Parameters:**
  - `id`: The `scan_id` returned from `POST /api/scans`.
- **Request Body:**
```json
{
  "confirmed_item": "Aluminum Beverage Can",
  "confirmed_category": "recyclable",
  "destination_id": "bin_metals_01",
  "idempotency_key": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
}
```

#### Success Response (`200 OK` or `201 Created`)
```json
{
  "confirmation_id": "conf_77182a9c",
  "scan_id": "scan_8f912c9b4e",
  "confirmed_item": "Aluminum Beverage Can",
  "confirmed_category": "recyclable",
  "destination_id": "bin_metals_01",
  "status": "recorded",
  "recorded_at": "2026-10-15T12:00:05Z",
  "updated_inventory_count": 142
}
```

> [!NOTE]
> If a request with an existing `idempotency_key` is received, the backend must return the previously confirmed record with `"status": "duplicate"` and HTTP 200 without double-incrementing inventory.

---

### 5.3 Digital Twin Snapshot
**`GET /api/twin/snapshot`**

Provides current bin fill levels, material breakdowns, and aggregate statistics for the dashboard.

#### Response (`200 OK`)
```json
{
  "snapshot_id": "snap_55102",
  "timestamp": "2026-10-15T12:00:10Z",
  "bins": [
    {
      "id": "bin_metals_01",
      "name": "Metals & Cans",
      "category": "recyclable",
      "current_fill_kg": 18.5,
      "max_capacity_kg": 25.0,
      "fill_percentage": 74.0,
      "last_updated": "2026-10-15T12:00:05Z"
    },
    {
      "id": "bin_organics_01",
      "name": "Compost & Organics",
      "category": "biodegradable",
      "current_fill_kg": 8.2,
      "max_capacity_kg": 20.0,
      "fill_percentage": 41.0,
      "last_updated": "2026-10-15T11:45:00Z"
    }
  ],
  "total_items_processed": 312,
  "active_routes": 4
}
```

---

### 5.4 Event History
**`GET /api/events?limit=50`**

Fetches recent timeline logs of scan classifications, confirmations, and alerts.

#### Response (`200 OK`)
```json
{
  "events": [
    {
      "event_id": "evt_912",
      "event_type": "scan_confirmed",
      "item_name": "Aluminum Beverage Can",
      "category": "recyclable",
      "destination_id": "bin_metals_01",
      "timestamp": "2026-10-15T12:00:05Z",
      "metadata": {
        "scan_id": "scan_8f912c9b4e",
        "match_score": 0.94
      }
    }
  ],
  "total_count": 1
}
```

---

### 5.5 Recommendations
**`GET /api/recommendations`**

Retrieves active AI recommendations derived from current twin capacity and sorting trends.

#### Response (`200 OK`)
```json
{
  "recommendations": [
    {
      "recommendation_id": "rec_01",
      "title": "Metals Bin Near Capacity",
      "description": "Metals & Cans bin is at 74% capacity with an influx of aluminum cans. Schedule pickup within 2 hours.",
      "severity": "medium",
      "action_type": "empty_bin",
      "created_at": "2026-10-15T12:00:06Z"
    }
  ],
  "generated_at": "2026-10-15T12:00:06Z",
  "based_on_snapshot_id": "snap_55102"
}
```

**`POST /api/recommendations/generate`**

Manually triggers an LLM synthesis job grounded in the latest inventory snapshot.

- **Request Body:**
```json
{
  "focus_category": "recyclable",
  "include_historical_events": true
}
```

---

### 5.6 Health & Model Diagnostics
- **`GET /api/health`**
  ```json
  {
    "status": "ok",
    "version": "1.0.0",
    "uptime_seconds": 3600,
    "timestamp": "2026-10-15T12:00:00Z"
  }
  ```
- **`GET /api/model/status`**
  ```json
  {
    "model_identifier": "yolov8-recycling-v2",
    "is_loaded": true,
    "device": "cuda",
    "inference_latency_ms": 142.5,
    "supported_categories": ["recyclable", "reusable", "biodegradable", "hazardous"],
    "version": "2.1.0"
  }
  ```

---

### 5.7 Live WebSocket Interface
**`WS /api/live`**

Allows client applications (scanner and dashboard) to receive immediate real-time notifications of confirmations or state updates without constant polling.

#### Message Envelope
```json
{
  "type": "item_confirmed",
  "payload": {
    "item_name": "Aluminum Beverage Can",
    "category": "recyclable",
    "destination_id": "bin_metals_01",
    "new_fill_percentage": 74.0
  },
  "timestamp": "2026-10-15T12:00:05Z"
}
```
