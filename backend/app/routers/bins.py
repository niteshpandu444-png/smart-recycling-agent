"""
Virtual Bins Router.
Provides endpoints for bin listing, creation, modification, history, and lifecycle operations (empty, transfer).
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import VirtualBin, MaterialEvent
from backend.app.adapters.schemas import (
    BinResponse,
    BinCreateRequest,
    BinUpdateRequest,
    BinTransferRequest,
    MaterialEventResponse,
)
from backend.app.services.digital_twin_service import calculate_bin_contamination_risk
from backend.app.services.material_service import (
    empty_virtual_bin,
    transfer_virtual_bin,
    BinNotFoundError,
    BinOverflowError,
    MaterialServiceError,
)

router = APIRouter(prefix="/api/bins", tags=["bins"])


def _build_bin_response(b: VirtualBin, db: Session) -> BinResponse:
    occ = round((b.current_inventory / b.capacity) * 100.0, 1) if b.capacity > 0 else None
    risk = calculate_bin_contamination_risk(db, b.id)
    return BinResponse(
        id=b.id,
        name=b.name,
        accepted_category=b.accepted_category,
        current_inventory=round(b.current_inventory, 2),
        capacity=round(b.capacity, 2),
        inventory_unit=b.inventory_unit,
        occupancy_percentage=occ,
        status=b.status,
        contamination_risk=risk,
    )


@router.get("", response_model=List[BinResponse], summary="List all virtual bins")
def list_bins_endpoint(db: Session = Depends(get_db)):
    bins = db.query(VirtualBin).order_by(VirtualBin.id).all()
    return [_build_bin_response(b, db) for b in bins]


@router.post(
    "",
    response_model=BinResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new virtual destination bin",
)
def create_bin_endpoint(request: BinCreateRequest, db: Session = Depends(get_db)):
    existing = db.query(VirtualBin).filter(VirtualBin.id == request.id).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Bin with ID '{request.id}' already exists.",
        )

    bin_obj = VirtualBin(
        id=request.id,
        name=request.name,
        accepted_category=request.accepted_category.lower().strip(),
        capacity=request.capacity,
        current_inventory=0.0,
        inventory_unit=request.inventory_unit,
        status="normal",
    )
    db.add(bin_obj)
    db.commit()
    db.refresh(bin_obj)
    return _build_bin_response(bin_obj, db)


@router.get("/{bin_id}", response_model=BinResponse, summary="Get details for a single bin")
def get_bin_endpoint(bin_id: str, db: Session = Depends(get_db)):
    bin_obj = db.query(VirtualBin).filter(VirtualBin.id == bin_id).first()
    if not bin_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bin '{bin_id}' not found.")
    return _build_bin_response(bin_obj, db)


@router.patch("/{bin_id}", response_model=BinResponse, summary="Update bin capacity or status")
def update_bin_endpoint(bin_id: str, request: BinUpdateRequest, db: Session = Depends(get_db)):
    bin_obj = db.query(VirtualBin).filter(VirtualBin.id == bin_id).first()
    if not bin_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bin '{bin_id}' not found.")

    if request.name is not None:
        bin_obj.name = request.name
    if request.capacity is not None:
        if request.capacity < bin_obj.current_inventory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"New capacity {request.capacity} is less than current inventory {bin_obj.current_inventory}.",
            )
        bin_obj.capacity = request.capacity
    if request.status is not None:
        bin_obj.status = request.status

    db.commit()
    db.refresh(bin_obj)
    return _build_bin_response(bin_obj, db)


@router.post("/{bin_id}/empty", response_model=BinResponse, summary="Empty/collect a bin")
def empty_bin_endpoint(
    bin_id: str,
    reason: Optional[str] = Query(None, description="Reason for collection/emptying"),
    db: Session = Depends(get_db),
):
    try:
        bin_obj = empty_virtual_bin(db, bin_id=bin_id, reason=reason)
        return _build_bin_response(bin_obj, db)
    except BinNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/transfer", status_code=status.HTTP_200_OK, summary="Transfer materials between bins")
def transfer_bin_endpoint(request: BinTransferRequest, db: Session = Depends(get_db)):
    try:
        transfer_virtual_bin(
            db=db,
            from_bin_id=request.from_bin_id,
            to_bin_id=request.to_bin_id,
            quantity=request.quantity,
            reason=request.reason,
        )
        return {
            "status": "success",
            "message": f"Transferred {request.quantity} from '{request.from_bin_id}' to '{request.to_bin_id}'.",
        }
    except BinNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BinOverflowError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except MaterialServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "/{bin_id}/history",
    response_model=List[MaterialEventResponse],
    summary="Get event audit history for a specific bin",
)
def get_bin_history_endpoint(
    bin_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    bin_obj = db.query(VirtualBin).filter(VirtualBin.id == bin_id).first()
    if not bin_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Bin '{bin_id}' not found.")

    events = (
        db.query(MaterialEvent)
        .filter((MaterialEvent.destination_bin_id == bin_id) | (MaterialEvent.source_bin_id == bin_id))
        .order_by(MaterialEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return events
