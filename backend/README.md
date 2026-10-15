# Smart Recycling Agent Vision API

This service classifies an uploaded image and returns a transient scan result.
It does not persist scans, create inventory records, confirm a user correction,
route materials through a Digital Twin, or make local-facility acceptance
decisions.

## API contract

- `GET /api/health` returns `{"status":"ok"}` while the API process is running,
  independently of model readiness.
- `GET /api/model/status` returns initialization state, model identifier,
  inference availability, and a safe diagnostic status.
- `POST /api/scans` accepts `multipart/form-data` with one image field named
  `file` and returns `ClassificationResponse` defined in `app/schemas.py`.

The response `scan_id` identifies this request only; it is not a persisted scan
or database key. `predicted_item` and `predicted_category` may both be null
when the model result is uncertain. `match_score` is the model's class score,
not a calibrated probability. The persistence and frontend clients should
treat the result as a vision suggestion and allow later correction. No
confirmation or database operation occurs in this API milestone.

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

Start the API from the repository root:

```powershell
backend/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
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
