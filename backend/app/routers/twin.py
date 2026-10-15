"""
Digital Twin Router.
Provides real-time Digital Twin state snapshots and what-if simulation endpoints.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.adapters.schemas import (
    DigitalTwinSnapshot,
    SimulationRequest,
    SimulationResponse,
)
from backend.app.services.digital_twin_service import (
    get_digital_twin_snapshot,
    simulate_what_if,
)

router = APIRouter(prefix="/api/twin", tags=["twin"])


@router.get(
    "/snapshot",
    response_model=DigitalTwinSnapshot,
    summary="Get real-time Digital Twin snapshot",
)
def get_twin_snapshot_endpoint(db: Session = Depends(get_db)):
    """
    Returns current simulated inventory, bin occupancy, contamination risk,
    and processing totals strictly computed from persisted database records.
    """
    return get_digital_twin_snapshot(db)


@router.post(
    "/simulate",
    response_model=SimulationResponse,
    status_code=status.HTTP_200_OK,
    summary="Run read-only what-if inventory simulation",
)
def simulate_twin_endpoint(
    request: SimulationRequest,
    db: Session = Depends(get_db),
):
    """
    Runs a hypothetical what-if projection of item additions or misclassification rates.
    Read-only: does not modify database records.
    """
    return simulate_what_if(db, request)
