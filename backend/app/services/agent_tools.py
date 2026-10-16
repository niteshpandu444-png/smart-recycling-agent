"""
Allowlisted read-only tools for the Recycling Intelligence Agent.
Grounded strictly in persisted Digital Twin database state and validated application policies.
No autonomous mutations are permitted in v1.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from backend.app.models import BatchScan, MaterialEntry, MaterialEvent, Scan, VirtualBin
from backend.app.services.digital_twin_service import (
    calculate_bin_contamination_risk,
    get_digital_twin_snapshot,
    get_filtered_events,
)
from backend.app.services.routing_rules import (
    CONFUSABLE_ITEM_KEYWORDS,
    CONFUSABLE_PAIRS,
    DEFAULT_CATEGORY_BIN_MAPPING,
    HOLDING_BIN_ID,
    MARGIN_THRESHOLD,
    is_confusable_pair,
)
from backend.app.vision import CLASS_POLICIES

logger = logging.getLogger("smart_recycling.agent_tools")


# ---------------------------------------------------------------------------
# Tool Argument Schemas (Pydantic validated)
# ---------------------------------------------------------------------------

class GetDigitalTwinSnapshotArgs(BaseModel):
    """Arguments for get_digital_twin_snapshot."""
    include_batch_activity: bool = Field(
        default=True,
        description="Whether to include recent mixed-waste batch activity summaries."
    )


class GetBinStatusArgs(BaseModel):
    """Arguments for get_bin_status."""
    bin_id: Optional[str] = Field(
        default=None,
        description="Optional bin ID to inspect (e.g. 'bin-plastic', 'bin-paper', 'bin-metal', 'bin-glass', 'bin-organic', 'bin-holding')."
    )
    status: Optional[str] = Field(
        default=None,
        description="Optional status filter ('normal', 'warning', 'full', 'maintenance')."
    )
    min_occupancy_percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Filter bins with occupancy percentage greater than or equal to this threshold (e.g. 75.0 for warning, 90.0 for critical)."
    )


class GetRecentEventsArgs(BaseModel):
    """Arguments for get_recent_events."""
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of recent material events to return (1-50, default 10)."
    )
    event_type: Optional[str] = Field(
        default=None,
        description="Optional event type filter ('confirmed', 'routed', 'reclassified', 'emptied', 'processed', 'reversal')."
    )
    category: Optional[str] = Field(
        default=None,
        description="Optional category filter (e.g. 'plastic', 'paper', 'metal', 'glass', 'organic')."
    )
    bin_id: Optional[str] = Field(
        default=None,
        description="Optional bin ID filter matching source or destination bin."
    )


class GetBatchReviewSummaryArgs(BaseModel):
    """Arguments for get_batch_review_summary."""
    batch_id: Optional[str] = Field(
        default=None,
        description="Optional specific batch scan ID to inspect in detail."
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of recent batch records to inspect (1-20, default 5)."
    )


class GetMaterialGuidanceArgs(BaseModel):
    """Arguments for get_material_guidance."""
    category: str = Field(
        min_length=1,
        max_length=50,
        description="Material or category name to check guidance for (e.g. 'plastic', 'paper', 'battery', 'metal', 'glass', 'biological', 'hazardous', 'reusable')."
    )


# ---------------------------------------------------------------------------
# Tool Implementations (Strictly Read-Only)
# ---------------------------------------------------------------------------

def tool_get_digital_twin_snapshot(db: Session, args: GetDigitalTwinSnapshotArgs) -> Tuple[Dict[str, Any], str]:
    """Retrieves full Digital Twin operational state."""
    snapshot = get_digital_twin_snapshot(db)

    bins_data = [
        {
            "id": b.id,
            "name": b.name,
            "accepted_category": b.accepted_category,
            "current_inventory": b.current_inventory,
            "capacity": b.capacity,
            "occupancy_percentage": b.occupancy_percentage,
            "status": b.status,
            "contamination_risk": b.contamination_risk,
        }
        for b in snapshot.bins
    ]

    result = {
        "timestamp": snapshot.timestamp.isoformat(),
        "total_confirmed_items": snapshot.total_confirmed_items,
        "category_inventory": snapshot.category_inventory,
        "bins": bins_data,
        "pending_verification_count": snapshot.pending_verification_count,
        "processing_totals": snapshot.processing_totals,
        "batch_scan_count": getattr(snapshot, "batch_scan_count", 0),
        "needs_review_scan_count": getattr(snapshot, "needs_review_scan_count", 0),
        "confirmed_from_batch_count": getattr(snapshot, "confirmed_from_batch_count", 0),
    }

    summary = (
        f"Digital Twin snapshot: {snapshot.total_confirmed_items:.0f} items confirmed across "
        f"{len(snapshot.bins)} virtual bins, {snapshot.pending_verification_count} item(s) in holding, "
        f"{getattr(snapshot, 'needs_review_scan_count', 0)} scans needing review."
    )
    return result, summary


def tool_get_bin_status(db: Session, args: GetBinStatusArgs) -> Tuple[Dict[str, Any], str]:
    """Retrieves current virtual bin occupancy, contamination risk, and capacity thresholds."""
    query = db.query(VirtualBin)

    if args.bin_id:
        query = query.filter(VirtualBin.id == args.bin_id.strip())
    if args.status:
        query = query.filter(VirtualBin.status == args.status.lower().strip())

    bins = query.order_by(VirtualBin.id).all()
    results = []

    for b in bins:
        occupancy = round((b.current_inventory / b.capacity) * 100.0, 1) if b.capacity > 0 else 0.0
        if args.min_occupancy_percentage is not None and occupancy < args.min_occupancy_percentage:
            continue

        contam_risk = calculate_bin_contamination_risk(db, b.id)
        results.append({
            "id": b.id,
            "name": b.name,
            "accepted_category": b.accepted_category,
            "current_inventory": round(b.current_inventory, 2),
            "capacity": round(b.capacity, 2),
            "occupancy_percentage": occupancy,
            "status": b.status,
            "contamination_risk": contam_risk,
            "is_nearing_capacity": occupancy >= 75.0,
            "is_critical": occupancy >= 90.0,
        })

    critical = [b["name"] for b in results if b["is_critical"]]
    warning = [b["name"] for b in results if b["is_nearing_capacity"] and not b["is_critical"]]

    summary_parts = [f"Found {len(results)} matching virtual bin(s)."]
    if critical:
        summary_parts.append(f"CRITICAL (>=90%): {', '.join(critical)}.")
    if warning:
        summary_parts.append(f"WARNING (>=75%): {', '.join(warning)}.")
    if not critical and not warning:
        summary_parts.append("All queried bins are operating within safe occupancy limits.")

    return {"bins": results, "count": len(results)}, " ".join(summary_parts)


def tool_get_recent_events(db: Session, args: GetRecentEventsArgs) -> Tuple[Dict[str, Any], str]:
    """Retrieves recent material confirmation, routing, emptying, or reclassification events."""
    items, next_cursor, total_count = get_filtered_events(
        db,
        limit=args.limit,
        category=args.category,
        bin_id=args.bin_id,
        event_type=args.event_type,
    )

    events_data = [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "affected_category": ev.affected_category,
            "quantity": ev.quantity,
            "unit": ev.unit,
            "source_bin_id": ev.source_bin_id,
            "destination_bin_id": ev.destination_bin_id,
            "timestamp": ev.timestamp.isoformat(),
        }
        for ev in items
    ]

    summary = (
        f"Retrieved {len(events_data)} of {total_count} recent material event(s)"
        f"{f' for event_type={args.event_type}' if args.event_type else ''}"
        f"{f' for category={args.category}' if args.category else ''}."
    )
    return {
        "events": events_data,
        "returned_count": len(events_data),
        "total_matching": total_count,
        "next_cursor": next_cursor,
    }, summary


def tool_get_batch_review_summary(db: Session, args: GetBatchReviewSummaryArgs) -> Tuple[Dict[str, Any], str]:
    """Retrieves mixed-waste batch scan activity, detected item counts, and items needing review."""
    if args.batch_id:
        batch = db.query(BatchScan).filter(BatchScan.id == args.batch_id.strip()).first()
        if not batch:
            return {
                "error": f"Batch scan '{args.batch_id}' not found.",
                "batch_id": args.batch_id,
            }, f"Batch scan '{args.batch_id}' was not found in database records."

        item_scans = []
        if batch.item_scan_ids:
            scans = db.query(Scan).filter(Scan.id.in_(batch.item_scan_ids)).all()
            for s in scans:
                item_scans.append({
                    "scan_id": s.id,
                    "predicted_category": s.predicted_category,
                    "confidence": round(s.confidence, 4),
                    "review_status": s.review_status,
                    "margin": round(s.margin, 4) if s.margin is not None else None,
                    "top_k_predictions": s.top_k_predictions,
                })

        result = {
            "batch_id": batch.id,
            "created_at": batch.created_at.isoformat(),
            "detection_count": int(batch.detection_count),
            "review_required_count": int(batch.review_required_count),
            "category_totals": batch.category_totals or {},
            "items": item_scans,
        }
        summary = (
            f"Batch {batch.id}: {batch.detection_count:.0f} item(s) detected, "
            f"{batch.review_required_count:.0f} requiring manual review."
        )
        return result, summary

    # General batch summary
    batches = db.query(BatchScan).order_by(desc(BatchScan.created_at)).limit(args.limit).all()
    batch_list = []
    total_detected = 0
    total_review_required = 0

    for b in batches:
        total_detected += int(b.detection_count)
        total_review_required += int(b.review_required_count)
        batch_list.append({
            "batch_id": b.id,
            "created_at": b.created_at.isoformat(),
            "detection_count": int(b.detection_count),
            "review_required_count": int(b.review_required_count),
            "category_totals": b.category_totals or {},
        })

    # Find recent pending scans across the system requiring review
    pending_scans = (
        db.query(Scan)
        .filter(Scan.review_status == "needs_review")
        .order_by(desc(Scan.created_at))
        .limit(10)
        .all()
    )

    pending_items_data = [
        {
            "scan_id": s.id,
            "predicted_category": s.predicted_category,
            "confidence": round(s.confidence, 4),
            "margin": round(s.margin, 4) if s.margin is not None else None,
            "review_status": s.review_status,
            "created_at": s.created_at.isoformat(),
        }
        for s in pending_scans
    ]

    result = {
        "recent_batches": batch_list,
        "batch_count": len(batch_list),
        "total_detected_in_sample": total_detected,
        "total_review_required_in_sample": total_review_required,
        "pending_review_scans": pending_items_data,
        "pending_review_count": len(pending_items_data),
    }

    summary = (
        f"Sampled {len(batch_list)} batch scan(s): {total_detected} detected items, "
        f"{total_review_required} marked for review. Currently {len(pending_items_data)} "
        f"scans actively awaiting review."
    )
    return result, summary


def tool_get_material_guidance(db: Session, args: GetMaterialGuidanceArgs) -> Tuple[Dict[str, Any], str]:
    """Retrieves standard application disposal policy, confusable material pairs, and destination bin."""
    cat = args.category.lower().strip()
    dest_bin = DEFAULT_CATEGORY_BIN_MAPPING.get(cat, HOLDING_BIN_ID)

    policy_info = CLASS_POLICIES.get(cat)
    display_name = policy_info[0] if policy_info else cat.title()
    classification_group = policy_info[1] if policy_info else ("holding" if cat == "holding" else "unclassified")
    guidance_text = (
        policy_info[2]
        if policy_info
        else "No direct model policy entry found. Unrecognized or ambiguous items must be routed to manual review."
    )

    confusable_with = [
        pair[1] if pair[0] == cat else pair[0]
        for pair in CONFUSABLE_PAIRS
        if cat in pair
    ]

    is_hazardous = cat in ("hazardous", "battery")
    curbside_accepted = cat in ("plastic", "paper", "metal", "glass") and not is_hazardous

    result = {
        "category": cat,
        "display_name": display_name,
        "classification_group": classification_group,
        "destination_bin_id": dest_bin,
        "guidance": guidance_text,
        "confusable_with": sorted(list(set(confusable_with))),
        "is_hazardous": is_hazardous,
        "curbside_accepted": curbside_accepted,
        "requires_holding": dest_bin == HOLDING_BIN_ID,
    }

    summary = (
        f"Material guidance for '{cat}': routes to bin '{dest_bin}'. Group: '{classification_group}'. "
        f"Curbside accepted: {curbside_accepted}. Confusable with: {confusable_with or 'None registered'}."
    )
    return result, summary


# ---------------------------------------------------------------------------
# Allowlist and Dispatch Registry
# ---------------------------------------------------------------------------

ALLOWLISTED_TOOLS = {
    "get_digital_twin_snapshot": {
        "schema": GetDigitalTwinSnapshotArgs,
        "fn": tool_get_digital_twin_snapshot,
        "description": "Retrieve the current Digital Twin snapshot including confirmed item totals, category inventory, bin statuses, capacities, and batch scan metrics.",
    },
    "get_bin_status": {
        "schema": GetBinStatusArgs,
        "fn": tool_get_bin_status,
        "description": "Retrieve current virtual bin occupancy, capacity, status, and contamination risk. Can filter by specific bin ID, status, or minimum occupancy percentage (e.g. 75% for warning, 90% for critical).",
    },
    "get_recent_events": {
        "schema": GetRecentEventsArgs,
        "fn": tool_get_recent_events,
        "description": "Retrieve recent material events (confirmed, routed, reclassified, emptied, processed) with optional filters by category, bin ID, or event type.",
    },
    "get_batch_review_summary": {
        "schema": GetBatchReviewSummaryArgs,
        "fn": tool_get_batch_review_summary,
        "description": "Retrieve mixed-waste batch scan activity, detected item totals, and pending scans requiring manual operator review.",
    },
    "get_material_guidance": {
        "schema": GetMaterialGuidanceArgs,
        "fn": tool_get_material_guidance,
        "description": "Retrieve handling guidance, confusable look-alike categories, destination bin mapping, and safety rules for a specific material or waste category.",
    },
}


class ToolExecutionError(Exception):
    pass


class UnknownToolError(ToolExecutionError):
    def __init__(self, tool_name: str):
        super().__init__(f"Tool '{tool_name}' is not in the allowlist. Allowed tools: {sorted(list(ALLOWLISTED_TOOLS.keys()))}")
        self.tool_name = tool_name


class InvalidToolArgsError(ToolExecutionError):
    def __init__(self, tool_name: str, errors: Any):
        super().__init__(f"Invalid arguments for tool '{tool_name}': {errors}")
        self.tool_name = tool_name
        self.errors = errors


def execute_allowlisted_tool(
    tool_name: str,
    raw_args: Dict[str, Any] | str,
    db: Session,
) -> Tuple[Dict[str, Any], str]:
    """
    Validates tool name against strict allowlist, validates arguments via Pydantic,
    and executes the tool against the database session.
    Returns (result_dict, human_summary).
    """
    if tool_name not in ALLOWLISTED_TOOLS:
        raise UnknownToolError(tool_name)

    spec = ALLOWLISTED_TOOLS[tool_name]
    arg_model = spec["schema"]
    tool_fn = spec["fn"]

    # Parse JSON string if necessary
    parsed_args = raw_args
    if isinstance(raw_args, str):
        try:
            parsed_args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError as exc:
            raise InvalidToolArgsError(tool_name, f"Malformed JSON arguments: {exc}")

    if not isinstance(parsed_args, dict):
        raise InvalidToolArgsError(tool_name, "Arguments must be a JSON object / dict.")

    try:
        validated_args = arg_model(**parsed_args)
    except ValidationError as val_err:
        raise InvalidToolArgsError(tool_name, val_err.errors())

    # Execute read-only tool
    return tool_fn(db, validated_args)


def get_openai_tool_definitions() -> List[Dict[str, Any]]:
    """Returns OpenAI-compatible tool specifications for the 5 allowlisted tools."""
    tools = []
    for name, spec in ALLOWLISTED_TOOLS.items():
        schema_cls = spec["schema"]
        json_schema = schema_cls.model_json_schema()
        # Clean schema for function-calling contract
        properties = json_schema.get("properties", {})
        required = json_schema.get("required", [])

        parameters: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = required

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": parameters,
            },
        })
    return tools
