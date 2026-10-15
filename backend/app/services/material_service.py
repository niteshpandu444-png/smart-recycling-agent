"""
Material Service — Confirmation, Reclassification, Routing, and Inventory Mutations.
Enforces atomicity, idempotency, provenance, and post-commit event notifications.
"""
import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.models import Scan, MaterialEntry, VirtualBin, MaterialEvent
from backend.app.adapters.schemas import MaterialConfirmRequest, ReclassifyRequest
from backend.app.adapters.event_publisher import publish_event
from backend.app.services.routing_rules import (
    evaluate_uncertainty,
    resolve_destination,
    HOLDING_BIN_ID,
)

logger = logging.getLogger("smart_recycling.material_service")


class MaterialServiceError(Exception):
    """Base exception for material service errors."""
    pass


class ScanNotFoundError(MaterialServiceError):
    pass


class ScanAlreadyConfirmedError(MaterialServiceError):
    pass


class InvalidCategoryError(MaterialServiceError):
    pass


class BinNotFoundError(MaterialServiceError):
    pass


class BinOverflowError(MaterialServiceError):
    def __init__(self, bin_id: str, capacity: float, current: float, added: float):
        self.bin_id = bin_id
        self.capacity = capacity
        self.current = current
        self.added = added
        super().__init__(
            f"Bin '{bin_id}' capacity exceeded: current {current} + added {added} > capacity {capacity}"
        )


class MaterialEntryNotFoundError(MaterialServiceError):
    pass


ALLOWED_CATEGORIES = {
    "plastic",
    "paper",
    "metal",
    "glass",
    "organic",
    "compostable",
    "holding",
}


def confirm_material(
    db: Session,
    request: MaterialConfirmRequest,
    idempotency_key: Optional[str] = None,
) -> MaterialEntry:
    """
    Executes the atomic material confirmation workflow:
    1. Checks idempotency key to prevent double processing.
    2. Verifies referenced scan exists.
    3. Verifies scan has not already been confirmed.
    4. Validates confirmed category.
    5. Resolves target destination bin.
    6. Updates virtual bin inventory with overflow guard.
    7. Creates MaterialEntry with full provenance.
    8. Records MaterialEvent.
    9. Commits atomically.
    10. Emits post-commit event.
    """
    effective_idempotency_key = idempotency_key or request.idempotency_key

    # 1. Idempotency Check
    if effective_idempotency_key:
        existing_event = (
            db.query(MaterialEvent)
            .filter(MaterialEvent.idempotency_key == effective_idempotency_key)
            .first()
        )
        if existing_event:
            logger.info(f"Idempotency hit for key: {effective_idempotency_key}")
            if existing_event.material_id:
                existing_entry = db.query(MaterialEntry).filter(MaterialEntry.id == existing_event.material_id).first()
                if existing_entry:
                    return existing_entry

    # 2. Verify Scan
    scan = db.query(Scan).filter(Scan.id == request.scan_id).first()
    if not scan:
        raise ScanNotFoundError(f"Scan with ID '{request.scan_id}' was not found.")

    # 3. Verify scan not already confirmed
    existing_entry = db.query(MaterialEntry).filter(MaterialEntry.scan_id == scan.id).first()
    if existing_entry or scan.review_status == "confirmed":
        raise ScanAlreadyConfirmedError(f"Scan '{scan.id}' has already been confirmed.")

    # 4. Validate category
    confirmed_cat = request.confirmed_category.lower().strip()
    if confirmed_cat not in ALLOWED_CATEGORIES:
        raise InvalidCategoryError(
            f"Invalid category '{request.confirmed_category}'. Allowed: {sorted(list(ALLOWED_CATEGORIES))}"
        )

    # 5. Resolve destination bin
    # Check if scan was flagged as ambiguous or low-confidence
    is_ambiguous, uncertainty_reason = evaluate_uncertainty(
        confidence=scan.confidence,
        predicted_category=scan.predicted_category,
        top_k=scan.top_k_predictions,
        margin=scan.margin,
        description=request.description,
    )

    # If user confirms without manual override or visual check, and item is ambiguous, route to holding
    target_bin_id = resolve_destination(
        category=confirmed_cat,
        is_ambiguous=is_ambiguous and request.confirmation_source == "model_accepted",
        requested_destination=request.destination_bin_id,
    )

    # Fetch destination bin
    target_bin = db.query(VirtualBin).filter(VirtualBin.id == target_bin_id).with_for_update().first()
    if not target_bin:
        raise BinNotFoundError(f"Destination bin '{target_bin_id}' does not exist.")

    # 6. Check Capacity & Overflow
    if target_bin.current_inventory + request.quantity > target_bin.capacity:
        raise BinOverflowError(
            bin_id=target_bin.id,
            capacity=target_bin.capacity,
            current=target_bin.current_inventory,
            added=request.quantity,
        )

    event_payload = {
        "uncertainty_reason": uncertainty_reason if is_ambiguous else None,
        "is_ambiguous": is_ambiguous,
        "description": request.description,
        "verification_answers": request.verification_answers,
    }

    try:
        # Update bin inventory & status
        target_bin.current_inventory += request.quantity
        ratio = target_bin.current_inventory / target_bin.capacity
        if ratio >= 1.0:
            target_bin.status = "full"
        elif ratio >= 0.75:
            target_bin.status = "warning"
        else:
            target_bin.status = "normal"

        # Update scan status
        scan.review_status = "confirmed"

        # Processing status
        proc_status = "holding" if target_bin.id == HOLDING_BIN_ID else "confirmed"

        # Create MaterialEntry
        entry = MaterialEntry(
            scan_id=scan.id,
            description=request.description or f"Confirmed {confirmed_cat}",
            category=confirmed_cat,
            confirmed_category=confirmed_cat,
            predicted_category=scan.predicted_category,
            quantity=request.quantity,
            unit=request.unit,
            destination=target_bin.id,
            processing_status=proc_status,
            confirmation_source=request.confirmation_source,
            confidence_at_confirmation=scan.confidence,
            verification_answers=request.verification_answers,
            is_demo=scan.is_demo,
        )
        db.add(entry)
        db.flush()  # assign entry.id

        # Record MaterialEvent
        event = MaterialEvent(
            event_type="confirmed",
            material_id=entry.id,
            scan_id=scan.id,
            destination_bin_id=target_bin.id,
            quantity=request.quantity,
            unit=request.unit,
            affected_category=confirmed_cat,
            payload=event_payload,
            idempotency_key=effective_idempotency_key,
            is_demo=scan.is_demo,
        )
        db.add(event)

        db.commit()
        db.refresh(entry)

    except Exception as e:
        db.rollback()
        logger.error(f"Transaction failed during confirmation: {e}")
        raise

    # 10. Post-Commit Event Broadcast
    publish_event(
        "material_confirmed",
        {
            "material_id": entry.id,
            "scan_id": scan.id,
            "category": entry.category,
            "destination_bin_id": target_bin.id,
            "quantity": entry.quantity,
            "status": entry.processing_status,
            "bin_inventory": target_bin.current_inventory,
            "bin_capacity": target_bin.capacity,
        },
    )

    return entry


def reclassify_material(
    db: Session,
    material_id: str,
    request: ReclassifyRequest,
    idempotency_key: Optional[str] = None,
) -> MaterialEntry:
    """
    Moves an item out of holding (or changes its category/bin):
    1. Validates material exists and target category is allowed.
    2. Atomically decrements from source bin.
    3. Atomically increments target bin.
    4. Records 'reclassified' event linking to original scan/material.
    5. Commits atomically.
    6. Emits post-commit event.
    """
    effective_idempotency_key = idempotency_key or request.idempotency_key

    # Idempotency check
    if effective_idempotency_key:
        existing_event = (
            db.query(MaterialEvent)
            .filter(MaterialEvent.idempotency_key == effective_idempotency_key)
            .first()
        )
        if existing_event and existing_event.material_id == material_id:
            existing_entry = db.query(MaterialEntry).filter(MaterialEntry.id == material_id).first()
            if existing_entry:
                return existing_entry

    entry = db.query(MaterialEntry).filter(MaterialEntry.id == material_id).with_for_update().first()
    if not entry:
        raise MaterialEntryNotFoundError(f"Material with ID '{material_id}' was not found.")

    target_cat = request.target_category.lower().strip()
    if target_cat not in ALLOWED_CATEGORIES:
        raise InvalidCategoryError(f"Target category '{request.target_category}' is not allowed.")

    source_bin_id = entry.destination
    target_bin_id = request.target_bin_id or resolve_destination(target_cat)

    source_bin = db.query(VirtualBin).filter(VirtualBin.id == source_bin_id).with_for_update().first()
    target_bin = db.query(VirtualBin).filter(VirtualBin.id == target_bin_id).with_for_update().first()

    if not target_bin:
        raise BinNotFoundError(f"Target bin '{target_bin_id}' does not exist.")

    # Guard overflow on target bin if moving to a different bin
    if source_bin_id != target_bin_id:
        if target_bin.current_inventory + entry.quantity > target_bin.capacity:
            raise BinOverflowError(
                bin_id=target_bin.id,
                capacity=target_bin.capacity,
                current=target_bin.current_inventory,
                added=entry.quantity,
            )

    try:
        # Update bins
        if source_bin and source_bin_id != target_bin_id:
            source_bin.current_inventory = max(0.0, source_bin.current_inventory - entry.quantity)
            src_ratio = source_bin.current_inventory / source_bin.capacity
            source_bin.status = "warning" if 0.75 <= src_ratio < 1.0 else ("normal" if src_ratio < 0.75 else "full")

        if source_bin_id != target_bin_id:
            target_bin.current_inventory += entry.quantity
            tgt_ratio = target_bin.current_inventory / target_bin.capacity
            target_bin.status = "full" if tgt_ratio >= 1.0 else ("warning" if tgt_ratio >= 0.75 else "normal")

        # Update entry
        entry.category = target_cat
        entry.confirmed_category = target_cat
        entry.destination = target_bin.id
        entry.processing_status = "confirmed" if target_bin.id != HOLDING_BIN_ID else "holding"
        if request.verification_answers:
            entry.verification_answers = request.verification_answers

        # Create reclassified event
        event = MaterialEvent(
            event_type="reclassified",
            material_id=entry.id,
            scan_id=entry.scan_id,
            source_bin_id=source_bin_id,
            destination_bin_id=target_bin.id,
            quantity=entry.quantity,
            unit=entry.unit,
            affected_category=target_cat,
            payload={
                "previous_category": entry.confirmed_category,
                "reason": request.reason,
                "verification_answers": request.verification_answers,
            },
            idempotency_key=effective_idempotency_key,
            is_demo=entry.is_demo,
        )
        db.add(event)

        db.commit()
        db.refresh(entry)

    except Exception as e:
        db.rollback()
        logger.error(f"Transaction failed during reclassification: {e}")
        raise

    publish_event(
        "material_reclassified",
        {
            "material_id": entry.id,
            "source_bin_id": source_bin_id,
            "destination_bin_id": target_bin.id,
            "new_category": target_cat,
            "quantity": entry.quantity,
        },
    )

    return entry


def empty_virtual_bin(db: Session, bin_id: str, reason: Optional[str] = None) -> VirtualBin:
    """Empties a virtual bin and logs an 'emptied' event for processing totals."""
    bin_obj = db.query(VirtualBin).filter(VirtualBin.id == bin_id).with_for_update().first()
    if not bin_obj:
        raise BinNotFoundError(f"Bin '{bin_id}' was not found.")

    cleared_quantity = bin_obj.current_inventory
    if cleared_quantity == 0:
        return bin_obj

    try:
        bin_obj.current_inventory = 0.0
        bin_obj.status = "normal"

        event = MaterialEvent(
            event_type="emptied",
            source_bin_id=bin_obj.id,
            quantity=cleared_quantity,
            unit=bin_obj.inventory_unit,
            affected_category=bin_obj.accepted_category,
            payload={"reason": reason or "Bin emptied by collection service"},
            is_demo=bin_obj.is_demo,
        )
        db.add(event)
        db.commit()
        db.refresh(bin_obj)
    except Exception:
        db.rollback()
        raise

    publish_event("bin_emptied", {"bin_id": bin_obj.id, "cleared_quantity": cleared_quantity})
    return bin_obj


def transfer_virtual_bin(
    db: Session,
    from_bin_id: str,
    to_bin_id: str,
    quantity: float,
    reason: Optional[str] = None,
) -> None:
    """Transfers materials between bins atomically and logs a 'transferred' event."""
    from_bin = db.query(VirtualBin).filter(VirtualBin.id == from_bin_id).with_for_update().first()
    to_bin = db.query(VirtualBin).filter(VirtualBin.id == to_bin_id).with_for_update().first()

    if not from_bin or not to_bin:
        raise BinNotFoundError("One or both bins do not exist.")

    if from_bin.current_inventory < quantity:
        raise MaterialServiceError(f"Insufficient inventory in source bin '{from_bin_id}'.")

    if to_bin.current_inventory + quantity > to_bin.capacity:
        raise BinOverflowError(to_bin.id, to_bin.capacity, to_bin.current_inventory, quantity)

    try:
        from_bin.current_inventory -= quantity
        to_bin.current_inventory += quantity

        event = MaterialEvent(
            event_type="transferred",
            source_bin_id=from_bin.id,
            destination_bin_id=to_bin.id,
            quantity=quantity,
            unit=from_bin.inventory_unit,
            affected_category=to_bin.accepted_category,
            payload={"reason": reason},
            is_demo=from_bin.is_demo,
        )
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()
        raise

    publish_event(
        "bin_transferred",
        {"from_bin_id": from_bin.id, "to_bin_id": to_bin.id, "quantity": quantity},
    )


def reverse_material_event(db: Session, event_id: str, reason: Optional[str] = None) -> MaterialEvent:
    """Creates a compensating reversal event, restoring inventory without deleting records."""
    orig_event = db.query(MaterialEvent).filter(MaterialEvent.id == event_id).with_for_update().first()
    if not orig_event:
        raise MaterialServiceError(f"Original event with ID '{event_id}' not found.")

    if orig_event.event_type == "reversal":
        raise MaterialServiceError("Cannot reverse a reversal event.")

    # Check if already reversed
    already_reversed = (
        db.query(MaterialEvent)
        .filter(
            MaterialEvent.event_type == "reversal",
            MaterialEvent.payload["original_event_id"].as_string() == orig_event.id,
        )
        .first()
    )
    if already_reversed:
        raise MaterialServiceError(f"Event '{event_id}' has already been reversed.")

    try:
        # Reversal logic depending on event type
        if orig_event.event_type == "confirmed" and orig_event.destination_bin_id:
            bin_obj = db.query(VirtualBin).filter(VirtualBin.id == orig_event.destination_bin_id).with_for_update().first()
            if bin_obj:
                bin_obj.current_inventory = max(0.0, bin_obj.current_inventory - orig_event.quantity)

            if orig_event.material_id:
                mat = db.query(MaterialEntry).filter(MaterialEntry.id == orig_event.material_id).first()
                if mat:
                    mat.processing_status = "reversed"

        rev_event = MaterialEvent(
            event_type="reversal",
            material_id=orig_event.material_id,
            scan_id=orig_event.scan_id,
            source_bin_id=orig_event.destination_bin_id,
            destination_bin_id=orig_event.source_bin_id,
            quantity=orig_event.quantity,
            unit=orig_event.unit,
            affected_category=orig_event.affected_category,
            payload={"original_event_id": orig_event.id, "reason": reason or "Administrative reversal"},
            is_demo=orig_event.is_demo,
        )
        db.add(rev_event)
        db.commit()
        db.refresh(rev_event)
    except Exception:
        db.rollback()
        raise

    publish_event("event_reversed", {"reversed_event_id": orig_event.id, "reversal_event_id": rev_event.id})
    return rev_event
