"""FastAPI application for transient image classification scans."""

from __future__ import annotations

import logging
import threading
import warnings
from contextlib import asynccontextmanager
from io import BytesIO
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, UnidentifiedImageError

from .schemas import ClassificationResponse
from .vision import classifier

logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_SIDE = 12_000
SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load in the background so process health and readiness remain distinct.
    threading.Thread(target=classifier.load, name="vision-model-loader", daemon=True).start()
    yield


app = FastAPI(
    title="Smart Recycling Agent Vision API",
    version="1.0.0",
    description="Transient computer-vision scan API. Scans are not persisted by this service.",
    lifespan=lifespan,
)


@app.get("/api/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report process liveness independently of model readiness."""
    return {"status": "ok"}


@app.get("/api/model/status", tags=["model"])
async def model_status() -> dict[str, str | bool]:
    """Report safe model readiness diagnostics without exception details."""
    return {
        "initialized_successfully": classifier.ready,
        "model_identifier": classifier.model_identifier,
        "inference_available": classifier.ready,
        "diagnostic_status": classifier.diagnostic_status,
    }


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
async def scan_image(request: Request, file: UploadFile = File(...)) -> ClassificationResponse:
    """Classify an uploaded image. No scan or inventory record is persisted."""
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

    return ClassificationResponse(
        scan_id=uuid4(),
        predicted_item=prediction.predicted_item,
        predicted_category=prediction.predicted_category,
        match_score=prediction.match_score,
        manual_review_recommended=prediction.manual_review_recommended,
        suggested_route=prediction.suggested_route,
        explanation=prediction.explanation,
        model_identifier=classifier.model_identifier,
        classification_status=prediction.classification_status,
    )
