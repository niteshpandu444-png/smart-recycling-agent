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


@router.get("/settings", summary="Get configurable simulation settings and thresholds")
def get_simulation_settings_endpoint(db: Session = Depends(get_db)):
    """
    Returns configurable simulation settings.
    NOTE: These are simulation settings, not physical sensor thresholds or facility policy.
    """
    from backend.app.models import SimulationSetting

    defaults = {
        "warning_threshold": 0.75,
        "critical_threshold": 0.90,
        "ambiguity_confidence_threshold": 0.70,
        "ambiguity_margin_threshold": 0.15,
    }
    rows = db.query(SimulationSetting).all()
    settings = {row.key: row.value for row in rows}
    for k, v in defaults.items():
        if k not in settings:
            settings[k] = v
    return {
        "simulation_label": "SIMULATION_SETTINGS",
        "settings": settings,
        "note": "Configurable thresholds for Digital Twin simulation and routing logic.",
    }


@router.patch("/settings", summary="Update configurable simulation settings")
def update_simulation_settings_endpoint(updates: dict, db: Session = Depends(get_db)):
    """
    Updates one or more simulation settings in the database.
    """
    from backend.app.models import SimulationSetting

    updated_keys = []
    for k, v in updates.items():
        row = db.query(SimulationSetting).filter(SimulationSetting.key == k).first()
        if not row:
            row = SimulationSetting(key=k, value=v, description=f"Simulation parameter {k}")
            db.add(row)
        else:
            row.value = v
        updated_keys.append(k)

    db.commit()
    return {"status": "success", "updated_settings": updated_keys}
