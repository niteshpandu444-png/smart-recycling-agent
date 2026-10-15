"""
Analytics Router.
Endpoints for model evaluation, confusion matrix, correction rates, flow graphs, and data exports.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.adapters.schemas import (
    CorrectionRateResponse,
    ConfusionMatrixResponse,
)
from backend.app.services.analytics_service import (
    get_correction_rates,
    get_confusion_matrix,
    export_corrected_scans_data,
    export_events_data,
    get_material_flow_data,
    calculate_fill_rates_and_time_to_full,
    check_database_health,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/corrections", response_model=CorrectionRateResponse, summary="Get prediction correction rates by category")
def get_corrections_endpoint(db: Session = Depends(get_db)):
    """
    Returns actual correction rates computed from persisted scans where predictions were modified.
    """
    return get_correction_rates(db)


@router.get("/confusion-matrix", response_model=ConfusionMatrixResponse, summary="Get classification confusion matrix")
def get_confusion_matrix_endpoint(db: Session = Depends(get_db)):
    """
    Returns confusion matrix of predicted vs confirmed classes, highlighting look-alike errors.
    """
    return get_confusion_matrix(db)


@router.get("/flow", summary="Get material flow graph data (Sankey format)")
def get_flow_endpoint(db: Session = Depends(get_db)):
    """
    Returns category -> virtual bin -> processing status aggregated flow links.
    """
    return get_material_flow_data(db)


@router.get("/fill-rates", summary="Get estimated fill rates and time-to-full projections")
def get_fill_rates_endpoint(
    window_hours: int = Query(24, ge=1, le=168, description="Historical event window in hours"),
    db: Session = Depends(get_db),
):
    """
    Linear projection of bin fill rates over recent events.
    Returns 'insufficient_data' if fewer than necessary events exist.
    """
    return calculate_fill_rates_and_time_to_full(db, window_hours=window_hours)


@router.get("/export/corrected-scans", summary="Export corrected scans in JSON or CSV format")
def export_corrected_scans_endpoint(
    format: str = Query("json", pattern="^(json|csv)$", description="Export format: json or csv"),
    db: Session = Depends(get_db),
):
    """
    Exports all scans that were corrected during confirmation or reclassification.
    Used by vision engineering for threshold calibration and dataset augmentation.
    """
    data = export_corrected_scans_data(db, format_type=format)
    if format == "csv":
        return Response(content=data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=corrected_scans.csv"})
    return data


@router.get("/export/events", summary="Export material events audit log in JSON or CSV format")
def export_events_endpoint(
    format: str = Query("json", pattern="^(json|csv)$", description="Export format: json or csv"),
    db: Session = Depends(get_db),
):
    """
    Exports complete material flow event history.
    """
    data = export_events_data(db, format_type=format)
    if format == "csv":
        return Response(content=data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=material_events.csv"})
    return data


@router.get("/health", summary="Service and database connectivity health check")
def health_check_endpoint(db: Session = Depends(get_db)):
    """
    Returns live connectivity status for the database engine.
    """
    return check_database_health(db)
