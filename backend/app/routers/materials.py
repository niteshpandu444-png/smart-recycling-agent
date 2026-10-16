"""
Materials Router.
Handles material confirmation, inspection, and reclassification operations.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import MaterialEntry
from backend.app.adapters.schemas import (
    BatchConfirmRequest,
    BatchConfirmResponse,
    MaterialConfirmRequest,
    MaterialEntryResponse,
    ReclassifyRequest,
)
from backend.app.services.material_service import (
    confirm_material,
    confirm_materials_batch,
    reclassify_material,
    ScanNotFoundError,
    ScanAlreadyConfirmedError,
    InvalidCategoryError,
    BinNotFoundError,
    BinOverflowError,
    MaterialEntryNotFoundError,
    MaterialServiceError,
)

router = APIRouter(prefix="/api/materials", tags=["materials"])


@router.post(
    "/confirm",
    response_model=MaterialEntryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Confirm a scanned material item",
)
def confirm_material_endpoint(
    request: MaterialConfirmRequest,
    db: Session = Depends(get_db),
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Atomically confirms a scanned material item:
    - Verifies the scan exists and hasn't been confirmed
    - Validates category and resolves destination bin
    - Updates bin inventory with overflow safety
    - Records an immutable MaterialEvent
    - Supports idempotent replays via Idempotency-Key header or body
    """
    idempotency_key = idempotency_key_header or request.idempotency_key
    try:
        entry = confirm_material(db, request, idempotency_key=idempotency_key)
        return entry
    except ScanNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ScanAlreadyConfirmedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (InvalidCategoryError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except BinNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BinOverflowError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MaterialServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/confirm-batch",
    response_model=BatchConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm several detected mixed-waste items",
)
def confirm_materials_batch_endpoint(
    request: BatchConfirmRequest,
    db: Session = Depends(get_db),
):
    """
    Confirms a reviewed batch of mixed-waste items, one item at a time through the
    existing single-item confirmation workflow.

    Each item keeps its own idempotency key and its own transaction, so an item
    that cannot be accepted (a full destination bin, an already-confirmed scan,
    an invalid category) fails only for itself and its reason is returned in
    ``results``. Callers must treat ``failed_count`` above zero as a partial
    outcome, not as a successful batch.
    """
    return confirm_materials_batch(db, request)


@router.get(
    "/{material_id}",
    response_model=MaterialEntryResponse,
    summary="Get confirmed material entry by ID",
)
def get_material_entry_endpoint(material_id: str, db: Session = Depends(get_db)):
    entry = db.query(MaterialEntry).filter(MaterialEntry.id == material_id).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Material entry '{material_id}' was not found.",
        )
    return entry


@router.post(
    "/{material_id}/reclassify",
    response_model=MaterialEntryResponse,
    summary="Reclassify material item and move between virtual bins",
)
def reclassify_material_endpoint(
    material_id: str,
    request: ReclassifyRequest,
    db: Session = Depends(get_db),
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    """
    Moves an ambiguous item out of holding (or changes its category/bin):
    - Atomically balances source and destination bins
    - Emits a 'reclassified' event linking to original scan
    - Preserves audit trail and provenance
    """
    idempotency_key = idempotency_key_header or request.idempotency_key
    try:
        entry = reclassify_material(db, material_id, request, idempotency_key=idempotency_key)
        return entry
    except MaterialEntryNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidCategoryError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except BinNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BinOverflowError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MaterialServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
