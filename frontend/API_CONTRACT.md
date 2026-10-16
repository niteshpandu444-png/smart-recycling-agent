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

`predicted_item`, `predicted_category`, and `match_score` may be `null` for an uncertain result. `match_score` is a model-specific score, not a calibrated probability. Before returning this response, the backend persists a pending `Scan` record and returns its primary key as `scan_id`. This does not change confirmed inventory; inventory changes only after the separate confirmation request succeeds.

### `POST /api/materials/confirm`

The confirmation body includes `scan_id` and a material-specific `confirmed_category`. Current accepted categories include `plastic`, `paper`, `metal`, `glass`, `organic`, `biodegradable`, `compostable`, `holding`, `hazardous`, and `reusable`. The broad scan categories (`recyclable`, `biodegradable`, etc.) are not interchangeable with material categories such as `glass` or `plastic`.

Optional request fields include `quantity`, `unit`, `destination_bin_id`, `confirmation_source`, `description`, `verification_answers`, and `idempotency_key`. If no destination bin ID is supplied, backend routing rules choose the destination. The client may also send the idempotency key in the `Idempotency-Key` header. A successful response is HTTP `201` and contains the persisted material entry (`id`, `scan_id`, `confirmed_category`, `destination`, `processing_status`, and timestamps). The UI reports success only after receiving that persisted response.

## Status and Digital Twin APIs

- `GET /api/health` returns `{ "status": "ok" }`.
- `GET /api/model/status` returns `initialized_successfully`, `model_identifier`, `inference_available`, and `diagnostic_status`.
- `GET /api/twin/snapshot` returns `timestamp`, `total_confirmed_items`, `category_inventory`, `bins`, `processing_totals`, and `pending_verification_count`.
- `GET /api/events` returns `{ "items": [...], "next_cursor": ..., "total_count": ... }`.
- `GET /api/recommendations` returns a list of recommendation records. `POST /api/recommendations/generate` accepts optional `{ "force_refresh": boolean }` and returns one recommendation record.

## Mixed-waste batch scanning

### `POST /api/scans/batch`

Multipart request with the image in the `file` field and an optional `source` field (`upload` or `camera`, default `upload`). Unlike `POST /api/scans`, this endpoint runs an object detector and returns **one result per detected object** instead of a single whole-image label.

The response is `batch_id`, `image_width`, `image_height`, `detection_count`, `review_required_count`, `detector_identifier`, `detector_license`, `detector_diagnostic_status`, `items`, and `notes`.

Each entry in `items` carries `item_id` (stable within the response), `scan_id` (a persisted **pending** scan), `detected_class`, `category`, `score`, `margin`, `box` (pixel and normalized coordinates), `review_status` (`ready` or `needs_review`), `review_reasons`, `suggested_destination`, `attempts_holding_bin`, `guidance`, an optional `cross_check`, and `metadata`.

Rules the client must respect:

- `items: []` is a real outcome meaning nothing was detected above the operating threshold. It is not an error and must not be rendered as a whole-image classification.
- `review_reasons` are the only justification for a `needs_review` item. Current reasons are `low_detection_score`, `unsupported_material_class`, `unsupported_destination`, `ambiguous_material_confidence`, `overlapping_material_conflict`, `featureless_crop_region`, and `cross_check_disagreement`.
- `score` is a detector comparison score, not a calibrated probability.
- This endpoint never changes inventory. Every item must still be confirmed.

### `POST /api/materials/confirm-batch`

Body is `{ "batch_id"?: string, "items": [...] }`. Each item accepts the same fields as `POST /api/materials/confirm`, plus an optional `item_id` echo.

Each item is applied independently through the existing single-item confirmation workflow, so it keeps its own idempotency key, its own transaction, and the same capacity and routing rules. The response is `confirmed_count`, `already_confirmed_count`, `failed_count`, and a `results` array whose entries carry `scan_id`, `status` (`confirmed`, `already_confirmed`, or `failed`), and `error` for failures.

A `failed_count` above zero is a partial outcome, not a success. The UI must report it as partial. Replaying the same items with the same idempotency keys cannot double-count inventory: a replayed key returns the originally recorded entry.

### `GET /api/model/detector/status`

Reports the mixed-waste detector separately from the single-item classifier: `initialized_successfully`, `inference_available`, `diagnostic_status`, `detector_identifier`, `detector_source`, `detector_license`, `detector_architecture`, `detector_class_names`, the detection thresholds, and `notes`. Kept separate so `GET /api/model/status` keeps exactly the fields its clients already depend on.

`GET /api/twin/snapshot` additionally returns batch activity: `batch_scan_count`, `detected_item_totals`, `needs_review_scan_count`, `confirmed_from_batch_count`, and `recent_batch_activity`. These count **detected** items and pending review work; they never inflate confirmed inventory.

## WebSocket

Connect to `ws://<backend-host>:8000/ws` (or `wss://` for TLS). The server sends an initial `{ "type": "snapshot", "data": ... }` message, followed by committed material event messages. No frontend inventory update should be inferred before the server confirms persistence.
