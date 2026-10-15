# Frontend API contract

These types follow the FastAPI application on `feat/backend-integration`. The backend remains the source of truth for classification, routing, and inventory. The canonical frontend TypeScript declarations are in `src/types/api.ts`.

## Scanner flow

### `POST /api/scans`

Send `multipart/form-data` with the image in field `file`. A successful response is the `ClassificationResponse` from `backend/app/schemas.py`:

```json
{
  "scan_id": "<uuid>",
  "predicted_item": "Glass",
  "predicted_category": "recyclable",
  "match_score": 0.91,
  "manual_review_recommended": false,
  "suggested_route": "Check local glass acceptance",
  "explanation": "Model and handling limitations...",
  "model_identifier": "configured-model",
  "classification_status": "success"
}
```

`predicted_item`, `predicted_category`, and `match_score` may be `null` for an uncertain result. `match_score` is a model-specific score, not a calibrated probability. A scan response is a classification result; persistence happens only after confirmation.

### `POST /api/materials/confirm`

The confirmation body includes `scan_id` and a material-specific `confirmed_category`. Current accepted categories include `plastic`, `paper`, `metal`, `glass`, `organic`, `biodegradable`, `compostable`, `holding`, `hazardous`, and `reusable`. The broad scan categories (`recyclable`, `biodegradable`, etc.) are not interchangeable with material categories such as `glass` or `plastic`.

Optional request fields include `quantity`, `unit`, `destination_bin_id`, `confirmation_source`, `description`, `verification_answers`, and `idempotency_key`. If no destination bin ID is supplied, backend routing rules choose the destination. The client may also send the idempotency key in the `Idempotency-Key` header. A successful response is HTTP `201` and contains the persisted material entry (`id`, `scan_id`, `confirmed_category`, `destination`, `processing_status`, and timestamps). The UI reports success only after receiving that persisted response.

## Status and Digital Twin APIs

- `GET /api/health` returns `{ "status": "ok" }`.
- `GET /api/model/status` returns `initialized_successfully`, `model_identifier`, `inference_available`, and `diagnostic_status`.
- `GET /api/twin/snapshot` returns `timestamp`, `total_confirmed_items`, `category_inventory`, `bins`, `processing_totals`, and `pending_verification_count`.
- `GET /api/events` returns `{ "items": [...], "next_cursor": ..., "total_count": ... }`.
- `GET /api/recommendations` returns a list of recommendation records. `POST /api/recommendations/generate` accepts optional `{ "force_refresh": boolean }` and returns one recommendation record.

## WebSocket

Connect to `ws://<backend-host>:8000/ws` (or `wss://` for TLS). The server sends an initial `{ "type": "snapshot", "data": ... }` message, followed by committed material event messages. No frontend inventory update should be inferred before the server confirms persistence.
