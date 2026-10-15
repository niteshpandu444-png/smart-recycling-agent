"""
Tests for Phase 2: Ambiguity Handling, Confusable-Pair Registry, Holding Bin,
Provenance Tracking, Reclassification, and Contamination Risk Calculation.
"""
import pytest
from backend.app.models import Scan, VirtualBin, MaterialEntry, MaterialEvent
from backend.app.services.routing_rules import (
    is_confusable_pair,
    evaluate_uncertainty,
    HOLDING_BIN_ID,
)


def test_confusable_pair_registry():
    """Verifies that registered confusable pairs are recognized symmetrically."""
    assert is_confusable_pair("paper", "plastic")
    assert is_confusable_pair("plastic", "paper")
    assert is_confusable_pair("compostable", "plastic")
    assert is_confusable_pair("plastic", "compostable")
    assert not is_confusable_pair("glass", "metal")
    assert not is_confusable_pair("paper", "glass")


def test_uncertainty_evaluation():
    """Verifies ambiguity detection on low confidence or narrow margin between confusable classes."""
    # 1. Low confidence alone
    is_amb, reason = evaluate_uncertainty(confidence=0.55, predicted_category="plastic")
    assert is_amb
    assert "below threshold" in reason.lower()

    # 2. Confusable pair with narrow margin
    top_k = [
        {"category": "paper", "score": 0.52},
        {"category": "plastic", "score": 0.48},
    ]
    is_amb, reason = evaluate_uncertainty(
        confidence=0.75,
        predicted_category="paper",
        top_k=top_k,
        margin=0.04,
    )
    assert is_amb
    assert "confusable pair" in reason.lower()

    # 3. High confidence non-confusable
    is_amb, reason = evaluate_uncertainty(confidence=0.95, predicted_category="metal")
    assert not is_amb


def test_confusable_prediction_routes_to_holding_bin(client, test_db, ambiguous_scan):
    """
    Verifies that a scan with confusable predictions (e.g. paper vs plastic)
    routes to the 'Needs Verification' holding bin, NOT plastic or paper.
    """
    holding_before = test_db.query(VirtualBin).filter(VirtualBin.id == HOLDING_BIN_ID).first().current_inventory
    plastic_before = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory

    payload = {
        "scan_id": ambiguous_scan.id,
        "confirmed_category": "paper",
        "quantity": 1.0,
        "confirmation_source": "model_accepted",
        "description": "Coffee cup with unknown lining",
    }
    resp = client.post("/api/materials/confirm", json=payload)
    assert resp.status_code == 201
    data = resp.json()

    assert data["destination"] == HOLDING_BIN_ID
    assert data["processing_status"] == "holding"
    assert data["predicted_category"] == "paper"
    assert data["confirmed_category"] == "paper"

    test_db.expire_all()
    holding_after = test_db.query(VirtualBin).filter(VirtualBin.id == HOLDING_BIN_ID).first().current_inventory
    plastic_after = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory

    assert holding_after == holding_before + 1.0
    assert plastic_after == plastic_before  # Untouched


def test_provenance_and_verification_checklist_persistence(client, test_db, sample_scan):
    """Verifies that checklist answers and provenance are persisted side-by-side with scan predictions."""
    verification_checklist = {
        "resin_identification_code": "5",
        "material_flexes_not_tears": True,
        "has_waxy_inner_lining": False,
        "holds_liquids": True,
    }
    payload = {
        "scan_id": sample_scan.id,
        "confirmed_category": "plastic",
        "quantity": 1.0,
        "confirmation_source": "user_label_check",
        "description": "Polypropylene takeaway container",
        "verification_answers": verification_checklist,
    }
    resp = client.post("/api/materials/confirm", json=payload)
    assert resp.status_code == 201
    entry_id = resp.json()["id"]

    entry = test_db.query(MaterialEntry).filter(MaterialEntry.id == entry_id).first()
    assert entry.confirmation_source == "user_label_check"
    assert entry.predicted_category == "plastic"
    assert entry.confirmed_category == "plastic"
    assert entry.confidence_at_confirmation == 0.92
    assert entry.verification_answers == verification_checklist


def test_reclassification_from_holding_bin(client, test_db, ambiguous_scan):
    """
    Verifies that moving an ambiguous item out of holding:
    1. Atomically decrements holding bin inventory.
    2. Atomically increments target bin inventory.
    3. Records a 'reclassified' event linking to original scan and material.
    """
    # 1. Initial confirmation to holding bin
    confirm_resp = client.post(
        "/api/materials/confirm",
        json={
            "scan_id": ambiguous_scan.id,
            "confirmed_category": "paper",
            "quantity": 2.0,
            "confirmation_source": "model_accepted",
        },
    )
    material_id = confirm_resp.json()["id"]

    holding_bin = test_db.query(VirtualBin).filter(VirtualBin.id == HOLDING_BIN_ID).first()
    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()

    h_before = holding_bin.current_inventory
    p_before = plastic_bin.current_inventory

    # 2. Reclassify with user verification answers
    reclassify_payload = {
        "target_category": "plastic",
        "target_bin_id": "bin-plastic",
        "reason": "Resin code #5 confirmed via label check",
        "verification_answers": {"resin_code": "5", "has_plastic_sheen": True},
    }
    reclass_resp = client.post(f"/api/materials/{material_id}/reclassify", json=reclassify_payload)
    assert reclass_resp.status_code == 200
    reclass_data = reclass_resp.json()

    assert reclass_data["destination"] == "bin-plastic"
    assert reclass_data["confirmed_category"] == "plastic"
    assert reclass_data["processing_status"] == "confirmed"

    test_db.expire_all()
    assert holding_bin.current_inventory == h_before - 2.0
    assert plastic_bin.current_inventory == p_before + 2.0

    # 3. Verify 'reclassified' event
    reclass_event = (
        test_db.query(MaterialEvent)
        .filter(MaterialEvent.material_id == material_id, MaterialEvent.event_type == "reclassified")
        .first()
    )
    assert reclass_event is not None
    assert reclass_event.source_bin_id == HOLDING_BIN_ID
    assert reclass_event.destination_bin_id == "bin-plastic"
    assert reclass_event.scan_id == ambiguous_scan.id
    assert reclass_event.quantity == 2.0


def test_idempotent_reclassification(client, test_db, ambiguous_scan):
    """Verifies that replaying reclassification with Idempotency-Key does not double-mutate inventory."""
    confirm_resp = client.post(
        "/api/materials/confirm",
        json={
            "scan_id": ambiguous_scan.id,
            "confirmed_category": "paper",
            "quantity": 1.0,
        },
    )
    material_id = confirm_resp.json()["id"]

    headers = {"Idempotency-Key": "reclass-idemp-001"}
    reclass_payload = {
        "target_category": "plastic",
        "reason": "Verified",
    }

    plastic_before = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory

    # First reclassification
    r1 = client.post(f"/api/materials/{material_id}/reclassify", json=reclass_payload, headers=headers)
    assert r1.status_code == 200

    # Replayed reclassification
    r2 = client.post(f"/api/materials/{material_id}/reclassify", json=reclass_payload, headers=headers)
    assert r2.status_code == 200

    test_db.expire_all()
    plastic_after = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory
    # Only added once
    assert plastic_after == plastic_before + 1.0


def test_pending_verification_count_in_snapshot(client, ambiguous_scan):
    """Verifies pending_verification in snapshot reflects actual holding bin count."""
    snap1 = client.get("/api/twin/snapshot").json()
    init_pending = snap1["pending_verification_count"]

    # Confirm ambiguous item
    confirm_resp = client.post(
        "/api/materials/confirm",
        json={
            "scan_id": ambiguous_scan.id,
            "confirmed_category": "paper",
            "quantity": 3.0,
        },
    )
    mat_id = confirm_resp.json()["id"]

    snap2 = client.get("/api/twin/snapshot").json()
    assert snap2["pending_verification_count"] == init_pending + 3

    # Reclassify out of holding
    client.post(
        f"/api/materials/{mat_id}/reclassify",
        json={"target_category": "plastic"},
    )

    snap3 = client.get("/api/twin/snapshot").json()
    assert snap3["pending_verification_count"] == init_pending


def test_contamination_risk_indicator(client, test_db):
    """
    Verifies that the per-bin contamination risk indicator:
    - Increases when items are confirmed with low confidence or after a confusable pair correction.
    - Is 0.0 when all items are verified with high confidence.
    """
    # 1. High confidence scan into glass
    scan_glass = Scan(
        id="scan-glass-safe",
        predicted_category="glass",
        confidence=0.98,
    )
    test_db.add(scan_glass)
    test_db.commit()

    client.post(
        "/api/materials/confirm",
        json={"scan_id": scan_glass.id, "confirmed_category": "glass", "quantity": 1.0},
    )

    snap_glass = client.get("/api/twin/snapshot").json()
    glass_bin = next(b for b in snap_glass["bins"] if b["id"] == "bin-glass")
    assert glass_bin["contamination_risk"] == 0.0

    # 2. Confusable correction into plastic (predicted paper, confirmed plastic with low confidence)
    scan_risk = Scan(
        id="scan-risk-1",
        predicted_category="paper",
        confidence=0.62,
    )
    test_db.add(scan_risk)
    test_db.commit()

    client.post(
        "/api/materials/confirm",
        json={
            "scan_id": scan_risk.id,
            "confirmed_category": "plastic",
            "destination_bin_id": "bin-plastic",
            "quantity": 1.0,
            "confirmation_source": "manual_override",
        },
    )

    snap_plastic = client.get("/api/twin/snapshot").json()
    plastic_bin = next(b for b in snap_plastic["bins"] if b["id"] == "bin-plastic")
    assert plastic_bin["contamination_risk"] > 0.0
