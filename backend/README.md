# Smart Recycling Agent Vision API

This service classifies an uploaded image and persists its prediction as a
`Scan` so the user can confirm or correct it later. Prediction alone does not
create a material entry or change Digital Twin inventory. Confirmed entries,
events, and bin state use the teammate's shared SQLAlchemy models and services.

## API contract

- `GET /api/health` returns `{"status":"ok"}` while the API process is running,
  independently of model readiness.
- `GET /api/model/status` returns initialization state, model identifier,
  inference availability, and a safe diagnostic status.
- HTTP browser access uses the comma-separated `CORS_ORIGINS` allowlist.
  Local development defaults to `http://localhost:3000` and
  `http://127.0.0.1:3000`; set the deployed frontend origin in `backend/.env`
  when the hosting URL is known. Credentials are disabled because this API
  does not use browser cookies or session authentication.
- `POST /api/scans` accepts `multipart/form-data` with one image field named
  `file`, commits its `Scan` record, and returns `ClassificationResponse`.
- `POST /api/materials/confirm` confirms or corrects a scan, creates a
  `MaterialEntry` and `MaterialEvent`, then updates inventory transactionally.
- The teammate routers are mounted at `/api/twin`, `/api/events`, `/api/bins`,
  `/api/recommendations`, and `/api/analytics` as well as `/api/materials`.
- `GET /api/twin/snapshot` reports current persisted bin and event-derived
  state. `/ws` sends a snapshot on connection and broadcasts post-commit events.

The response `scan_id` is the UUID primary key of the committed Scan record.
`predicted_item` and `predicted_category` may both be null when the model result
is uncertain; that scan is stored with `review_status="needs_review"` and
remains confirmable. The Scan model stores a material-specific predicted
category, confidence, model identifier, review state, top model classes, and
score margin. The response's `classification_status` maps to the persisted
review state; `suggested_route` and `explanation` remain response-only because
the teammate's Scan schema has no corresponding fields. `match_score` is the
model's class score, not a calibrated probability.

The model's material classes are mapped for persistence as follows: battery →
hazardous; biological → organic; cardboard → paper; glass, metal, paper, and
plastic retain their material classes; trash → holding. The scan response
keeps the existing broad application categories. The confirmation endpoint
uses material-specific categories. Hazardous and reusable categories are
accepted but route to the existing `bin-holding`; the Digital Twin does not
currently define a dedicated authorized hazardous-waste or reuse destination.
The frontend should submit a specific material category when confirming a
recyclable scan rather than the broad `recyclable` response category.

## Mixed-waste batch scanning

`POST /api/scans/batch` runs a **second, separate** model. The original classifier
is whole-image and single-label; it cannot report how many items a photo contains
or where they are, so it is never presented as a multi-object detector.

| Property | Value |
| --- | --- |
| Artifact | `backend/models/waste-detector.onnx` (downloaded on first use) |
| Source | https://huggingface.co/Jeremy341/MIRA-AI (`mira_exp019.onnx`) |
| Architecture | Ultralytics YOLO11n detect head, exported to ONNX (training stack 8.4.112) |
| Input / output | `float32[1,3,640,640]` → `float32[1,9,8400]` (4 box + 5 class scores, no embedded NMS) |
| Classes | `glass`, `metal`, `paper`, `plastic`, `trash` |
| Size | 10,607,296 bytes |
| Licence | **AGPL-3.0**, declared in the artifact's own ONNX metadata. The Hugging Face model card states MIT. Review before deploying. |

Preprocessing is the Ultralytics letterbox convention (aspect-preserving resize to
640×640, neutral-grey pad). Post-processing is class-aware NMS at IoU 0.45, then a
same-object collapse at IoU 0.75 that keeps the losing label as evidence for
review. No accuracy figure is claimed: the artifact was never evaluated here
against a labelled waste benchmark.

Detected items are persisted as **pending** `scans` rows grouped by a `batch_scans`
record. A batch scan never mutates inventory; `POST /api/materials/confirm-batch`
applies the existing single-item confirmation workflow per item.

Known limitations, measured on this artifact:

- Recall is limited. On the repository's own test images it detected paper at 0.80
  and glass at 0.88, but plastic at only 0.20–0.35, and it misses items entirely.
- It can be confident about a featureless region: a uniformly coloured image
  produced `glass` at 0.83. Crop texture analysis flags those for review.
- There is no battery, organic, or electronic-waste class.
- The detector reports material appearance, not object identity (a bottle is
  labelled by material, not as a bottle).

## If the detector is ever retrained from user corrections

Nothing in this repository trains or fine-tunes a model at runtime, and no
learning pipeline exists. `GET /api/analytics/corrections` and
`GET /api/analytics/confusion-matrix` expose correction history that *could* seed
such work, but treating them as training data requires safeguards this project has
not implemented:

- **Data quality.** Corrections are not labels. They carry no independent
  verification, no inter-annotator agreement, and they are biased towards whatever
  the model already finds, so hard cases are under-represented. Only items with a
  recorded, deliberate `user_corrected` provenance should be candidates.
- **Holdout discipline.** A labelled evaluation set must be split before any
  training run. Accuracy must never be reported from the data used to tune the
  model, and the existing test images are not a benchmark.
- **Stratified review.** Each material class needs its own held-out sample,
  including the classes the detector currently never predicts (battery, organic)
  and the confusable pairs registered in `routing_rules.py`.
- **Regression gates.** A candidate must match or beat the current artifact on the
  held-out set *and* preserve the safety behaviour: low-confidence and unsupported
  items must still route to review rather than being auto-approved.
- **Provenance.** Retraining changes inference behaviour, so it changes the
  AGPL-3.0 obligations described below and must be recorded as a deliberate,
  reviewed release rather than a background job.

## Model and inference

The API uses the Apache-2.0-licensed
[`SriramRokkam/wastewise-garbage-cls` model](https://huggingface.co/SriramRokkam/wastewise-garbage-cls),
specifically `wastewise-yolo.onnx` (published size about 5.81 MB). The model
card identifies it as a YOLOv8n classification export with eight output
classes in this order: battery, biological, cardboard, glass, metal, paper,
plastic, trash. It documents RGB 224×224 input, values normalized to [0, 1],
NCHW layout, and softmax scores. The implementation checks the ONNX input and
output metadata at load time instead of assuming tensor names or shapes.

Inference requires `onnxruntime`, `numpy`, and Pillow. It runs locally through
ONNX Runtime's CPU execution provider and does not require PyTorch,
Transformers, Ultralytics, a paid API, or a GPU. If the default artifact is
absent, the first model initialization downloads it from the repository to a
temporary `.part` file, validates its size and ONNX metadata, then atomically
renames it to `backend/models/wastewise-yolo.onnx`. A failed or interrupted
download is not retained as a valid model. Subsequent starts reuse the
validated artifact. Model files are ignored by Git.

Set `VISION_MODEL_PATH` in `backend/.env` to use a different local ONNX artifact.
Relative paths resolve under `backend/`. The default target is
`backend/models/wastewise-yolo.onnx`. Initial setup needs network access to
install packages and download the model. No credentials are needed.

The explicit application mapping is separate from the model's class list:

- Battery → hazardous; use an authorized battery collection or hazardous-waste
  service.
- Biological → biodegradable; local compost or food-scrap rules apply.
- Cardboard, glass, metal, paper, and plastic → recyclable suggestions, subject
  to local acceptance and preparation requirements.
- Trash → uncertain/manual review.
- The model has no dedicated electronic-waste class. A material prediction
  does not establish that an item is or is not e-waste.

No class is automatically labeled reusable. In particular, a glass prediction
does not establish that the object is clean, intact, suitable for reuse, or
accepted by a local facility. The current top-score threshold (0.45) and
top-to-second margin threshold (0.12) are conservative engineering heuristics
for requesting manual review; they are not validated accuracy thresholds or
guarantees. The publisher reports its own validation result, but it has not
been independently reproduced here and should not be treated as this API's
measured accuracy.

## Setup and startup (PowerShell)

From the repository root:

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --upgrade pip
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
```

The shared persistence layer reads `DATABASE_URL` from the process environment
and defaults to `sqlite:///./smart_recycling.db`. Application startup calls the
existing idempotent `init_db()` setup; it creates missing tables and baseline
bins without dropping existing data. Alembic configuration and the initial
revision are included for explicit schema migrations. Use an isolated database
URL for tests; never point tests at a developer database.

The six service routers declare their own `/api/...` prefixes and are mounted
without additional prefixes. The WebSocket publisher contract is synchronous
`register_event_listener(listener)` where each listener receives
`(event_type: str, payload: dict)` after the publisher's transaction commits.
The app bridges those callbacks onto its event loop, removes the listener on
shutdown, drops disconnected clients, and sends the current database snapshot
to clients when they connect or reconnect.

The `/ws` endpoint checks a supplied browser `Origin` against the same
`CORS_ORIGINS` allowlist. Clients without an `Origin` header (for example,
non-browser service clients) are permitted; deployments that require browser
clients should configure the frontend's exact origin. Set `CORS_ORIGINS` to the
exact deployed frontend origin, without a path or wildcard. HTTPS deployments
must configure the frontend to use `wss://` for the WebSocket connection.

Recommendations use the existing deterministic fallback grounded in the
current persisted Digital Twin state. This integration adds no external LLM
provider or credentials.

Start the API from the repository root:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The model initializes at API startup and may take time on first run while the
artifact downloads. Open `http://127.0.0.1:8000/docs` for the interactive API
contract.

## Tests and verification

Run deterministic API and ONNX-adapter tests with:

```powershell
backend/.venv/Scripts/python.exe -m pytest backend/tests -q
```

These automated tests use mocked ONNX sessions and do not verify real model
initialization or classification accuracy. Keep real model initialization and
image-inference smoke results separately identified. A synthetic image can
check that the graph executes, but it cannot establish classification
accuracy.
