"""
Digital Twin Service.
Computes real-time state snapshots, processing totals, contamination risk,
and read-only what-if simulations strictly from persisted database records.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc

from backend.app.models import VirtualBin, MaterialEntry, MaterialEvent, Scan, SnapshotRecord
from backend.app.adapters.schemas import (
    DigitalTwinSnapshot,
    BinSnapshot,
    SimulationRequest,
    SimulationResponse,
    SimulatedBinEffect,
)
from backend.app.services.routing_rules import HOLDING_BIN_ID, resolve_destination, is_confusable_pair


def calculate_bin_contamination_risk(db: Session, bin_id: str) -> float:
    """
    Computes a simulation indicator [0.0 - 1.0] representing contamination risk in a bin.
    Grounds calculation strictly in persisted events:
    - Share of items routed to this bin that had low confidence (< 0.70)
    - Items confirmed after a confusable pair correction (e.g. paper <-> plastic)
    """
    entries = db.query(MaterialEntry).filter(MaterialEntry.destination == bin_id).all()
    if not entries:
        return 0.0

    risk_weighted_count = 0.0
    total_count = 0.0

    for entry in entries:
        qty = entry.quantity
        total_count += qty

        is_risk = False
        # Condition 1: Low confidence at confirmation
        if entry.confidence_at_confirmation is not None and entry.confidence_at_confirmation < 0.70:
            is_risk = True

        # Condition 2: Correction across confusable categories
        if entry.predicted_category and entry.confirmed_category:
            if is_confusable_pair(entry.predicted_category, entry.confirmed_category):
                is_risk = True

        if is_risk:
            risk_weighted_count += qty

    if total_count == 0:
        return 0.0

    return round(min(1.0, risk_weighted_count / total_count), 3)


def get_digital_twin_snapshot(db: Session) -> DigitalTwinSnapshot:
    """
    Generates a live Digital Twin snapshot strictly from persisted database records.
    """
    bins = db.query(VirtualBin).order_by(VirtualBin.id).all()

    bin_snapshots: List[BinSnapshot] = []
    category_inventory: Dict[str, float] = {}

    for b in bins:
        occupancy = None
        if b.capacity > 0:
            occupancy = round((b.current_inventory / b.capacity) * 100.0, 1)

        contam_risk = calculate_bin_contamination_risk(db, b.id)

        bin_snapshots.append(
            BinSnapshot(
                id=b.id,
                name=b.name,
                accepted_category=b.accepted_category,
                current_inventory=round(b.current_inventory, 2),
                capacity=round(b.capacity, 2),
                inventory_unit=b.inventory_unit,
                occupancy_percentage=occupancy,
                status=b.status,
                contamination_risk=contam_risk,
                last_updated=getattr(b, "updated_at", None),
                needs_service=bool(occupancy is not None and occupancy >= 90.0),
            )
        )

        cat = b.accepted_category
        category_inventory[cat] = category_inventory.get(cat, 0.0) + b.current_inventory

    # Total confirmed items across all non-holding bins
    total_confirmed = (
        db.query(func.coalesce(func.sum(MaterialEntry.quantity), 0.0))
        .filter(MaterialEntry.processing_status.in_(["confirmed", "processed"]))
        .scalar()
    )

    # Pending verification count: items in holding bin or awaiting review
    holding_bin = db.query(VirtualBin).filter(VirtualBin.id == HOLDING_BIN_ID).first()
    pending_verification = int(holding_bin.current_inventory if holding_bin else 0)

    # Processing totals from real 'emptied' or 'processed' events
    processing_rows = (
        db.query(
            MaterialEvent.affected_category,
            func.coalesce(func.sum(MaterialEvent.quantity), 0.0),
        )
        .filter(MaterialEvent.event_type.in_(["emptied", "processed"]))
        .group_by(MaterialEvent.affected_category)
        .all()
    )
    processing_totals = {cat: float(qty) for cat, qty in processing_rows}

    active_routes = len([b for b in bin_snapshots if b.current_inventory > 0])

    snapshot = DigitalTwinSnapshot(
        timestamp=datetime.now(timezone.utc),
        total_confirmed_items=float(total_confirmed),
        total_items_processed=float(total_confirmed),
        active_routes=active_routes,
        category_inventory={k: round(v, 2) for k, v in category_inventory.items()},
        bins=bin_snapshots,
        processing_totals=processing_totals,
        pending_verification_count=pending_verification,
    )

    return snapshot


def record_snapshot_state(db: Session, is_demo: bool = False) -> SnapshotRecord:
    """
    Captures and persists a SnapshotRecord containing the current inventory and bin states.
    Written synchronously during committed inventory-changing transactions.
    """
    bins = db.query(VirtualBin).order_by(VirtualBin.id).all()
    total_confirmed = (
        db.query(func.coalesce(func.sum(MaterialEntry.quantity), 0.0))
        .filter(MaterialEntry.processing_status.in_(["confirmed", "processed"]))
        .scalar()
    )

    bin_states: Dict[str, Any] = {}
    for b in bins:
        occupancy = None
        if b.capacity > 0:
            occupancy = round((b.current_inventory / b.capacity) * 100.0, 1)
        bin_states[b.id] = {
            "name": b.name,
            "category": b.accepted_category,
            "current_inventory": round(b.current_inventory, 2),
            "capacity": round(b.capacity, 2),
            "inventory_unit": b.inventory_unit,
            "occupancy_percentage": occupancy,
            "status": b.status,
        }

    rec = SnapshotRecord(
        total_items=float(total_confirmed),
        bin_states=bin_states,
        is_demo=is_demo,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(rec)
    return rec


def get_snapshot_history(db: Session, limit: int = 50) -> List[SnapshotRecord]:
    """
    Retrieves historical snapshot records ordered newest first.
    """
    return (
        db.query(SnapshotRecord)
        .order_by(desc(SnapshotRecord.timestamp), desc(SnapshotRecord.id))
        .limit(limit)
        .all()
    )


def get_filtered_events(
    db: Session,
    limit: int = 50,
    cursor: Optional[str] = None,
    last_event_id: Optional[str] = None,
    category: Optional[str] = None,
    bin_id: Optional[str] = None,
    event_type: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Tuple[List[MaterialEvent], Optional[str], int]:
    """
    Retrieves filtered events with cursor-based pagination and reconnect event replay.
    """
    query = db.query(MaterialEvent)

    if category:
        query = query.filter(MaterialEvent.affected_category == category.lower().strip())
    if bin_id:
        query = query.filter(
            (MaterialEvent.destination_bin_id == bin_id) | (MaterialEvent.source_bin_id == bin_id)
        )
    if event_type:
        query = query.filter(MaterialEvent.event_type == event_type.lower().strip())
    if start_time:
        query = query.filter(MaterialEvent.timestamp >= start_time)
    if end_time:
        query = query.filter(MaterialEvent.timestamp <= end_time)

    # Reconnect replay: if last_event_id is provided, fetch events committed AFTER that event
    if last_event_id:
        last_event = db.query(MaterialEvent).filter(MaterialEvent.id == last_event_id).first()
        if last_event:
            query = query.filter(
                (MaterialEvent.timestamp > last_event.timestamp)
                | (
                    (MaterialEvent.timestamp == last_event.timestamp)
                    & (MaterialEvent.id > last_event.id)
                )
            )

    total_count = query.count()

    # Cursor ordering for pagination (fetching older events)
    if cursor:
        cursor_event = db.query(MaterialEvent).filter(MaterialEvent.id == cursor).first()
        if cursor_event:
            query = query.filter(
                (MaterialEvent.timestamp < cursor_event.timestamp)
                | (
                    (MaterialEvent.timestamp == cursor_event.timestamp)
                    & (MaterialEvent.id < cursor_event.id)
                )
            )

    if last_event_id:
        # For reconnect replay, order ascending so the client can process missed events in arrival order
        items = query.order_by(asc(MaterialEvent.timestamp), asc(MaterialEvent.id)).limit(limit + 1).all()
    else:
        # For standard history query, order descending (newest first)
        items = query.order_by(desc(MaterialEvent.timestamp), desc(MaterialEvent.id)).limit(limit + 1).all()

    next_cursor = None
    if len(items) > limit:
        next_cursor = items[limit - 1].id
        items = items[:limit]

    return items, next_cursor, total_count


def simulate_what_if(db: Session, request: SimulationRequest) -> SimulationResponse:
    """
    Read-only what-if projection.
    Simulates hypothetical additions and misclassification impacts on current bins.
    NEVER writes to the database.
    """
    bins = db.query(VirtualBin).all()
    bin_map = {b.id: b for b in bins}

    # Track simulated inventory additions per bin
    simulated_added: Dict[str, float] = {b.id: 0.0 for b in bins}
    potential_contamination: Dict[str, float] = {b.id: 0.0 for b in bins}

    misclassification_rates = request.hypothetical_misclassification_rates or {}

    for item in request.hypothetical_additions:
        target_bin_id = item.destination_bin_id or resolve_destination(item.category)
        if target_bin_id in simulated_added:
            simulated_added[target_bin_id] += item.quantity

            # If a misclassification rate is specified for this bin, compute potential misrouted units
            m_rate = misclassification_rates.get(target_bin_id, 0.0)
            if m_rate > 0.0:
                potential_contamination[target_bin_id] += item.quantity * m_rate

    projections: List[SimulatedBinEffect] = []
    summary_notes: List[str] = []

    for b in bins:
        starting = b.current_inventory
        added = simulated_added[b.id]
        projected = starting + added
        capacity = b.capacity

        occ_pct = None
        if capacity > 0:
            occ_pct = round((projected / capacity) * 100.0, 1)

        overflow = projected > capacity
        if overflow:
            proj_status = "overflow_risk"
            summary_notes.append(
                f"Bin '{b.name}' ({b.id}) will overflow: projected {projected:.1f} exceeds capacity {capacity:.1f}"
            )
        elif occ_pct and occ_pct >= 90.0:
            proj_status = "critical"
            summary_notes.append(f"Bin '{b.name}' ({b.id}) will reach critical occupancy ({occ_pct}%).")
        elif occ_pct and occ_pct >= 75.0:
            proj_status = "warning"
        else:
            proj_status = "normal"

        contam_items = round(potential_contamination.get(b.id, 0.0), 1)
        if contam_items > 0:
            summary_notes.append(
                f"Bin '{b.name}' has {contam_items} potential misclassified items under hypothetical error rate."
            )

        projections.append(
            SimulatedBinEffect(
                bin_id=b.id,
                bin_name=b.name,
                starting_inventory=round(starting, 2),
                projected_inventory=round(projected, 2),
                capacity=round(capacity, 2),
                projected_occupancy_percentage=occ_pct,
                projected_status=proj_status,
                would_overflow=overflow,
                potential_contamination_items=contam_items,
            )
        )

    return SimulationResponse(
        simulation_label="HYPOTHETICAL_SIMULATION_READ_ONLY",
        timestamp=datetime.now(timezone.utc),
        bin_projections=projections,
        summary_notes=summary_notes,
    )
