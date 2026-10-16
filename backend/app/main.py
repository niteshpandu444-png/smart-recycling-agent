"""FastAPI application for transient image classification scans."""

from __future__ import annotations

import asyncio
import logging
import threading
import warnings
from contextlib import asynccontextmanager
from io import BytesIO
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from .adapters.event_publisher import register_event_listener, unregister_event_listener
from .config import CORS_ORIGINS
from .database import SessionLocal, get_db, init_db
from .models import BatchScan, Scan
from .routers import agent, analytics, bins, events, materials, recommendations, twin
from .services.batch_scan_service import (
    DETECTOR_CLASS_TO_APP_CATEGORY,
    analyze_detections,
    make_classifier_cross_check,
)
from .services.digital_twin_service import get_digital_twin_snapshot
from .schemas import (
    BatchScanItem,
    BatchScanResponse,
    ClassificationResponse,
    CropCrossCheck,
    DetectionBox,
    DetectorStatusResponse,
)
from .vision import PERSISTED_CATEGORY_BY_MODEL_CLASS, classifier
from .vision_detector import (
    DETECTION_SCORE_THRESHOLD,
    DETECTOR_ARCHITECTURE,
    NMS_IOU_THRESHOLD,
    SAME_OBJECT_IOU_THRESHOLD,
    detector,
)

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_SIDE = 12_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}
# How the mixed-waste image arrived. Recorded for batch provenance only.
BATCH_SOURCES = {"upload", "camera"}
# Honest statements returned with every batch result. These describe what the
# detector can and cannot tell a user, and what a detected item does not mean.
BATCH_NOTES = [
    "Detected items are pending records only. A batch scan never changes inventory; "
    "inventory moves only when an item is separately confirmed.",
    "The detector reports material appearance (glass, metal, paper, plastic, trash). It has no "
    "battery, organic, or electronic-waste class and cannot verify item condition or local acceptance.",
    "Scores are detector comparison scores, not calibrated probabilities. This project did not "
    "evaluate the detector against a labelled waste benchmark, so no accuracy figure is claimed.",
    "Recall is limited: items the detector does not find above the operating threshold are absent "
    "from this result rather than guessed at.",
]


class WebSocketManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, event: dict) -> None:
        stale: list[WebSocket] = []
        for connection in tuple(self.connections):
            try:
                await connection.send_json(event)
            except (WebSocketDisconnect, RuntimeError, OSError):
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)

    async def close_all(self) -> None:
        for connection in tuple(self.connections):
            try:
                await connection.close(code=1001)
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass
            self.disconnect(connection)


websocket_manager = WebSocketManager()


def _publish_to_websockets(event_type: str, payload: dict) -> None:
    loop = getattr(app.state, "websocket_loop", None)
    if loop is None or not loop.is_running():
        return
    try:
        asyncio.run_coroutine_threadsafe(
            websocket_manager.broadcast({"type": event_type, "data": payload}),
            loop,
        )
    except RuntimeError:
        logger.info("WebSocket event skipped because the application loop is stopping")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Use the shared, idempotent database initialization; never reset existing data.
    init_db()
    app.state.websocket_loop = asyncio.get_running_loop()
    register_event_listener(_publish_to_websockets)
    # Load in the background so process health and readiness remain distinct.
    # The detector is a second independent artifact; a missing or invalid one
    # must not stop the process or the existing single-item classifier.
    threading.Thread(target=classifier.load, name="vision-model-loader", daemon=True).start()
    threading.Thread(target=detector.load, name="waste-detector-loader", daemon=True).start()
    try:
        yield
    finally:
        unregister_event_listener(_publish_to_websockets)
        await websocket_manager.close_all()
        app.state.websocket_loop = None


app = FastAPI(
    title="Smart Recycling Agent Vision API",
    version="1.0.0",
    description="Computer-vision scans are persisted for user confirmation; inventory changes only on confirmation.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(CORS_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Accept", "Content-Type", "Idempotency-Key"],
)

# Each teammate router already declares its full /api/... prefix.
for service_router in (
    materials.router,
    twin.router,
    events.router,
    recommendations.router,
    bins.router,
    analytics.router,
    agent.router,
):
    app.include_router(service_router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """Send a database snapshot on connection, then committed material events."""
    origin = websocket.headers.get("origin")
    if origin and origin.rstrip("/") not in CORS_ORIGINS:
        await websocket.close(code=1008, reason="Origin is not allowed.")
        return
    await websocket_manager.connect(websocket)
    session = SessionLocal()
    try:
        snapshot = get_digital_twin_snapshot(session)
        await websocket.send_json({"type": "snapshot", "data": snapshot.model_dump(mode="json")})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("WebSocket session ended (%s)", type(exc).__name__)
        try:
            await websocket.close(code=1011)
        except (WebSocketDisconnect, RuntimeError, OSError):
            pass
    finally:
        session.close()
        websocket_manager.disconnect(websocket)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report process liveness independently of model readiness."""
    return {"status": "ok"}


@app.get("/api/model/status", tags=["model"])
async def model_status() -> dict[str, str | bool]:
    """Report safe single-item classifier readiness without exception details."""
    return {
        "initialized_successfully": classifier.ready,
        "model_identifier": classifier.model_identifier,
        "inference_available": classifier.ready,
        "diagnostic_status": classifier.diagnostic_status,
    }


@app.get("/api/model/detector/status", response_model=DetectorStatusResponse, tags=["model"])
async def detector_status() -> DetectorStatusResponse:
    """Report mixed-waste detector readiness and provenance.

    Kept separate from ``/api/model/status`` so the existing single-item status
    contract keeps exactly the fields its clients already depend on.
    """
    return DetectorStatusResponse(
        initialized_successfully=detector.ready,
        inference_available=detector.ready,
        diagnostic_status=detector.diagnostic_status,
        detector_identifier=detector.model_identifier,
        detector_source=detector.source,
        detector_license=detector.license,
        detector_architecture=DETECTOR_ARCHITECTURE,
        detector_class_names=list(detector.class_names),
        detection_score_threshold=DETECTION_SCORE_THRESHOLD,
        nms_iou_threshold=NMS_IOU_THRESHOLD,
        same_object_iou_threshold=SAME_OBJECT_IOU_THRESHOLD,
        notes=BATCH_NOTES,
    )


async def _read_upload(file: UploadFile, request: Request) -> bytes:
    # Content-Length includes multipart framing, so allow a small envelope overhead.
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_BYTES + 128 * 1024:
                raise HTTPException(status_code=413, detail="Upload exceeds the 8 MB image limit.")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid Content-Length header.") from None
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 8 MB image limit.")
    return data


def _decode_image(data: bytes) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(data))
            actual_format = image.format
            if actual_format not in SUPPORTED_FORMATS:
                raise HTTPException(status_code=415, detail="Supported image formats are JPEG, PNG, and WebP.")
            width, height = image.size
            if width < 16 or height < 16 or width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(status_code=422, detail="Image dimensions are outside the supported range.")
            image.load()  # Force full decode while the byte buffer is still available.
            return image.convert("RGB")
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=413, detail="Image dimensions exceed the safe decoding limit.") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(status_code=422, detail="File content is not a valid, decodable image.") from None


@app.post("/api/scans", response_model=ClassificationResponse, tags=["scans"])
async def scan_image(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ClassificationResponse:
    """Classify an upload and persist its prediction for later confirmation."""
    try:
        data = await _read_upload(file, request)
        image = _decode_image(data)
    finally:
        await file.close()

    if not classifier.ready:
        image.close()
        raise HTTPException(status_code=503, detail="Vision model is unavailable.")
    try:
        prediction = await run_in_threadpool(classifier.predict, image)
    except Exception as exc:
        logger.error("Vision inference failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Vision inference failed; no classification was produced.") from None
    finally:
        image.close()

    if prediction.model_class not in PERSISTED_CATEGORY_BY_MODEL_CLASS or prediction.match_score is None:
        raise HTTPException(status_code=503, detail="Vision result could not be represented for persistence.")

    scan_id = uuid4()
    persisted_scan = Scan(
        id=str(scan_id),
        image_url=None,
        predicted_category=PERSISTED_CATEGORY_BY_MODEL_CLASS[prediction.model_class],
        confidence=prediction.match_score,
        model_identifier=classifier.model_identifier,
        review_status=(
            "needs_review"
            if prediction.manual_review_recommended or prediction.classification_status == "uncertain"
            else "pending"
        ),
        top_k_predictions=[
            {"category": name, "score": score}
            for name, score in prediction.top_k_predictions
        ],
        margin=prediction.margin,
    )
    try:
        await run_in_threadpool(_commit_scan, db, persisted_scan)
    except Exception as exc:
        logger.error("Scan persistence failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Scan result could not be stored.") from None

    return ClassificationResponse(
        scan_id=scan_id,
        predicted_item=prediction.predicted_item,
        predicted_category=prediction.predicted_category,
        match_score=prediction.match_score,
        manual_review_recommended=prediction.manual_review_recommended,
        suggested_route=prediction.suggested_route,
        explanation=prediction.explanation,
        model_identifier=classifier.model_identifier,
        classification_status=prediction.classification_status,
    )


def _commit_scan(db: Session, scan: Scan) -> None:
    try:
        db.add(scan)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _commit_batch(db: Session, batch: BatchScan, scans: list[Scan]) -> None:
    """Persist the batch record and all of its pending item scans together."""
    try:
        db.add(batch)
        for scan in scans:
            db.add(scan)
        db.commit()
    except Exception:
        db.rollback()
        raise


@app.post("/api/scans/batch", response_model=BatchScanResponse, tags=["scans"])
async def scan_batch(
    request: Request,
    file: UploadFile = File(...),
    source: str = Form("upload"),
    db: Session = Depends(get_db),
) -> BatchScanResponse:
    """Detect and analyse every waste object in one mixed-waste image.

    Runs the object detector to locate items, then persists one *pending* scan
    per detected item and one batch record linking them. This endpoint never
    changes inventory: each item must still be confirmed individually.

    An image with no detectable objects returns an empty ``items`` list. That is
    a real result and is never back-filled with a stand-in detection.
    """
    if source not in BATCH_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported batch source. Allowed: {sorted(BATCH_SOURCES)}.",
        )

    try:
        data = await _read_upload(file, request)
        image = _decode_image(data)
    finally:
        await file.close()

    if not detector.ready:
        image.close()
        raise HTTPException(status_code=503, detail="Mixed-waste detector is unavailable.")

    try:
        detections = await run_in_threadpool(detector.detect, image)
        analyses = await run_in_threadpool(
            analyze_detections,
            image,
            detections,
            detector_identifier=detector.model_identifier,
            cross_check=make_classifier_cross_check(classifier),
        )
        image_width, image_height = image.size
    except Exception as exc:
        logger.error("Mixed-waste detection failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Mixed-waste detection failed; no results were produced.",
        ) from None
    finally:
        image.close()

    batch_id = uuid4()
    scan_records: list[Scan] = []
    category_totals: dict[str, float] = {}
    review_required = 0
    for analysis in analyses:
        # ``top_k_predictions`` feeds the existing ambiguity check at confirmation
        # time, so it carries application categories rather than detector classes.
        top_k = [{"category": analysis.category, "score": round(float(analysis.score), 6)}]
        if analysis.runner_up is not None:
            top_k.append(
                {
                    "category": DETECTOR_CLASS_TO_APP_CATEGORY.get(analysis.runner_up[0], "holding"),
                    "score": round(float(analysis.runner_up[1]), 6),
                }
            )
        scan_records.append(
            Scan(
                id=str(uuid4()),
                image_url=None,
                predicted_category=analysis.category,
                confidence=analysis.score,
                model_identifier=detector.model_identifier,
                review_status="needs_review"
                if analysis.review_status == "needs_review"
                else "pending",
                top_k_predictions=top_k,
                margin=analysis.margin,
            )
        )
        category_totals[analysis.category] = category_totals.get(analysis.category, 0.0) + 1.0
        if analysis.review_status == "needs_review":
            review_required += 1

    batch_record = BatchScan(
        id=str(batch_id),
        detector_identifier=detector.model_identifier,
        source=source,
        image_width=float(image_width),
        image_height=float(image_height),
        detection_count=float(len(scan_records)),
        review_required_count=float(review_required),
        category_totals=category_totals,
        item_scan_ids=[record.id for record in scan_records],
    )
    try:
        await run_in_threadpool(_commit_batch, db, batch_record, scan_records)
    except Exception as exc:
        logger.error("Batch scan persistence failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Batch scan result could not be stored.") from None

    items = [
        BatchScanItem(
            item_id=analysis.item_id,
            scan_id=record.id,
            detected_class=analysis.detected_class,
            category=analysis.category,
            score=analysis.score,
            margin=analysis.margin,
            box=DetectionBox(
                x1=analysis.box_pixels[0],
                y1=analysis.box_pixels[1],
                x2=analysis.box_pixels[2],
                y2=analysis.box_pixels[3],
                normalized_x1=analysis.box_normalized[0],
                normalized_y1=analysis.box_normalized[1],
                normalized_x2=analysis.box_normalized[2],
                normalized_y2=analysis.box_normalized[3],
            ),
            review_status=analysis.review_status,
            review_reasons=list(analysis.review_reasons),
            suggested_destination=analysis.suggested_destination,
            attempts_holding_bin=analysis.attempts_holding_bin,
            guidance=analysis.guidance,
            cross_check=None
            if analysis.cross_check is None
            else CropCrossCheck(
                model_class=analysis.cross_check.model_class,
                category=analysis.cross_check.category,
                score=analysis.cross_check.score,
                model_identifier=analysis.cross_check.model_identifier,
            ),
            metadata=analysis.metadata,
        )
        for analysis, record in zip(analyses, scan_records)
    ]

    return BatchScanResponse(
        batch_id=batch_id,
        image_width=image_width,
        image_height=image_height,
        detection_count=len(items),
        review_required_count=review_required,
        detector_identifier=detector.model_identifier,
        detector_license=detector.license,
        detector_diagnostic_status=detector.diagnostic_status,
        items=items,
        notes=BATCH_NOTES
        + (
            [
                "No objects were detected above the operating threshold. This is an empty "
                "detection result, not a classification of the whole image."
            ]
            if not items
            else []
        ),
    )
