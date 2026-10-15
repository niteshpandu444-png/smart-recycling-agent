"""
Analytics Service.
Calculates correction rates, confusion matrix, material flow graphs,
time-to-full projections, and CSV/JSON exports strictly from persisted records.
"""
import io
import csv
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, text

from backend.app.models import MaterialEntry, MaterialEvent, VirtualBin, Scan
from backend.app.services.routing_rules import is_confusable_pair


def get_correction_rates(db: Session) -> Dict[str, Any]:
    """
    Computes correction rate per predicted category and overall across all confirmed scans.
    """
    entries = (
        db.query(MaterialEntry)
        .filter(MaterialEntry.predicted_category.isnot(None))
        .all()
    )

    stats: Dict[str, Dict[str, int]] = {}
    total_confirmed = len(entries)
    total_corrected = 0

    for e in entries:
        pred = e.predicted_category.lower()
        conf = e.confirmed_category.lower()
        if pred not in stats:
            stats[pred] = {"total_scanned": 0, "corrected_count": 0}

        stats[pred]["total_scanned"] += 1
        if pred != conf:
            stats[pred]["corrected_count"] += 1
            total_corrected += 1

    category_rates = []
    for cat, data in stats.items():
        rate = round(data["corrected_count"] / data["total_scanned"], 3) if data["total_scanned"] > 0 else 0.0
        category_rates.append({
            "category": cat,
            "total_scanned": data["total_scanned"],
            "corrected_count": data["corrected_count"],
            "correction_rate": rate,
        })

    overall_rate = round(total_corrected / total_confirmed, 3) if total_confirmed > 0 else 0.0

    return {
        "category_rates": category_rates,
        "overall_correction_rate": overall_rate,
        "total_confirmed_scans": total_confirmed,
    }


def get_confusion_matrix(db: Session) -> Dict[str, Any]:
    """
    Builds a confusion matrix of predicted vs confirmed categories from persisted records.
    Highlights high-risk confusions between biodegradable/paper and plastic.
    """
    entries = (
        db.query(MaterialEntry)
        .filter(MaterialEntry.predicted_category.isnot(None))
        .all()
    )

    categories = sorted(list({e.predicted_category.lower() for e in entries} | {e.confirmed_category.lower() for e in entries}))
    if not categories:
        categories = ["plastic", "paper", "metal", "glass", "organic"]

    matrix: Dict[str, Dict[str, int]] = {pred: {conf: 0 for conf in categories} for pred in categories}
    high_risk_confusions = []

    for e in entries:
        pred = e.predicted_category.lower()
        conf = e.confirmed_category.lower()
        if pred in matrix and conf in matrix[pred]:
            matrix[pred][conf] += 1

        if pred != conf and is_confusable_pair(pred, conf):
            high_risk_confusions.append({
                "material_id": e.id,
                "scan_id": e.scan_id,
                "predicted": pred,
                "confirmed": conf,
                "confidence": e.confidence_at_confirmation,
                "confirmation_source": e.confirmation_source,
            })

    return {
        "categories": categories,
        "matrix": matrix,
        "high_risk_confusions": high_risk_confusions,
    }


def export_corrected_scans_data(db: Session, format_type: str = "json") -> Any:
    """
    Exports corrected scans for vision model retraining and threshold calibration.
    """
    entries = (
        db.query(MaterialEntry)
        .filter(
            MaterialEntry.predicted_category.isnot(None),
            MaterialEntry.predicted_category != MaterialEntry.confirmed_category,
        )
        .all()
    )

    records = []
    for e in entries:
        records.append({
            "material_id": e.id,
            "scan_id": e.scan_id,
            "predicted_category": e.predicted_category,
            "confirmed_category": e.confirmed_category,
            "confidence_at_confirmation": e.confidence_at_confirmation,
            "confirmation_source": e.confirmation_source,
            "quantity": e.quantity,
            "unit": e.unit,
            "verification_answers": json.dumps(e.verification_answers) if e.verification_answers else "",
            "created_at": e.created_at.isoformat(),
        })

    if format_type.lower() == "csv":
        output = io.StringIO()
        fieldnames = [
            "material_id",
            "scan_id",
            "predicted_category",
            "confirmed_category",
            "confidence_at_confirmation",
            "confirmation_source",
            "quantity",
            "unit",
            "verification_answers",
            "created_at",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        return output.getvalue()

    return records


def export_events_data(db: Session, format_type: str = "json") -> Any:
    """
    Exports material events for external audit or data pipeline ingestion.
    """
    events = db.query(MaterialEvent).order_by(MaterialEvent.timestamp.asc()).all()

    records = []
    for ev in events:
        records.append({
            "id": ev.id,
            "event_type": ev.event_type,
            "material_id": ev.material_id,
            "scan_id": ev.scan_id,
            "source_bin_id": ev.source_bin_id,
            "destination_bin_id": ev.destination_bin_id,
            "quantity": ev.quantity,
            "unit": ev.unit,
            "affected_category": ev.affected_category,
            "idempotency_key": ev.idempotency_key,
            "is_demo": ev.is_demo,
            "timestamp": ev.timestamp.isoformat(),
        })

    if format_type.lower() == "csv":
        output = io.StringIO()
        fieldnames = [
            "id",
            "event_type",
            "material_id",
            "scan_id",
            "source_bin_id",
            "destination_bin_id",
            "quantity",
            "unit",
            "affected_category",
            "idempotency_key",
            "is_demo",
            "timestamp",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
        return output.getvalue()

    return records


def get_material_flow_data(db: Session) -> Dict[str, Any]:
    """
    Provides aggregated category -> bin -> status flow data suitable for Sankey diagrams.
    """
    nodes = []
    links = []

    # Aggregated category -> destination bin
    flows = (
        db.query(
            MaterialEntry.category,
            MaterialEntry.destination,
            MaterialEntry.processing_status,
            func.sum(MaterialEntry.quantity).label("total_quantity"),
        )
        .group_by(MaterialEntry.category, MaterialEntry.destination, MaterialEntry.processing_status)
        .all()
    )

    node_set = set()
    for cat, dest, status_name, qty in flows:
        cat_node = f"category:{cat}"
        dest_node = f"bin:{dest}"
        status_node = f"status:{status_name}"

        node_set.add(cat_node)
        node_set.add(dest_node)
        node_set.add(status_node)

        links.append({"source": cat_node, "target": dest_node, "value": float(qty)})
        links.append({"source": dest_node, "target": status_node, "value": float(qty)})

    nodes = [{"id": n, "label": n.split(":", 1)[1], "type": n.split(":", 1)[0]} for n in sorted(list(node_set))]

    return {
        "nodes": nodes,
        "links": links,
        "note": "Flow computed strictly from confirmed material entries.",
    }


def calculate_fill_rates_and_time_to_full(
    db: Session,
    window_hours: int = 24,
) -> Dict[str, Any]:
    """
    Estimates fill rates and time-to-full per bin using linear projection over recent events.
    Returns 'insufficient_data' if there are too few events.
    """
    bins = db.query(VirtualBin).all()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)

    estimates = {}

    for b in bins:
        # Sum incoming confirmed additions in window
        recent_additions = (
            db.query(func.coalesce(func.sum(MaterialEvent.quantity), 0.0))
            .filter(
                MaterialEvent.destination_bin_id == b.id,
                MaterialEvent.event_type.in_(["confirmed", "reclassified", "transferred"]),
                MaterialEvent.timestamp >= cutoff,
            )
            .scalar()
        )

        remaining_capacity = max(0.0, b.capacity - b.current_inventory)
        rate_per_hour = float(recent_additions) / window_hours if window_hours > 0 else 0.0

        if rate_per_hour > 0:
            hours_to_full = round(remaining_capacity / rate_per_hour, 1)
            estimates[b.id] = {
                "bin_name": b.name,
                "current_inventory": b.current_inventory,
                "capacity": b.capacity,
                "fill_rate_per_hour": round(rate_per_hour, 2),
                "estimated_hours_to_full": hours_to_full,
                "status": "active_estimate",
                "window_hours": window_hours,
            }
        else:
            estimates[b.id] = {
                "bin_name": b.name,
                "current_inventory": b.current_inventory,
                "capacity": b.capacity,
                "fill_rate_per_hour": 0.0,
                "estimated_hours_to_full": None,
                "status": "insufficient_data",
                "window_hours": window_hours,
                "reason": "No incoming material events recorded within observation window.",
            }

    return {
        "projection_type": "linear_historical_window",
        "observation_window_hours": window_hours,
        "bin_estimates": estimates,
    }


def check_database_health(db: Session) -> Dict[str, Any]:
    """
    Verifies database connectivity with a live query.
    """
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": f"connection_error: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
