"""
Tests for Phase 4: Recommendation Service.
Covers deterministic fallback, context hashing and caching, output validation,
lifecycle status transitions, evidence linking, rate limiting, and grounded Q&A.
"""
import pytest
from backend.app.models import VirtualBin, Recommendation
from backend.app.services.recommendation_service import (
    generate_recommendation,
    reset_rate_limits,
    RATE_LIMIT_MAX_REQUESTS,
    RateLimitExceededError,
)


def setup_function():
    reset_rate_limits()


def test_deterministic_fallback_no_llm(client, test_db):
    """Verifies recommendations work reliably with no LLM configured, labeled as deterministic fallback."""
    resp = client.post("/api/recommendations/generate")
    assert resp.status_code == 201
    data = resp.json()

    assert data["generation_method"] == "deterministic_fallback"
    assert "System Status Normal" in data["title"]
    assert "supporting_data" in data
    assert "bin_ids" in data["supporting_data"]
    assert data["status"] == "new"


def test_recommendation_caching_by_data_hash(client, test_db):
    """Verifies that calling generate without state change returns cached entity without creating new row."""
    resp1 = client.post("/api/recommendations/generate")
    assert resp1.status_code == 201
    rec_id_1 = resp1.json()["id"]

    # Calling again without state change must hit cache
    resp2 = client.post("/api/recommendations/generate")
    assert resp2.status_code == 201
    rec_id_2 = resp2.json()["id"]

    assert rec_id_1 == rec_id_2
    assert test_db.query(Recommendation).count() == 1

    # Force refresh creates a new entity
    resp3 = client.post("/api/recommendations/generate", json={"force_refresh": True})
    assert resp3.status_code == 201
    rec_id_3 = resp3.json()["id"]
    assert rec_id_3 != rec_id_1


def test_ambiguity_aware_recommendation(client, test_db, ambiguous_scan):
    """Verifies that items in the holding bin trigger an ambiguity-aware recommendation."""
    client.post(
        "/api/materials/confirm",
        json={
            "scan_id": ambiguous_scan.id,
            "confirmed_category": "paper",
            "quantity": 2.0,
            "confirmation_source": "model_accepted",
        },
    )

    resp = client.post("/api/recommendations/generate", json={"force_refresh": True})
    assert resp.status_code == 201
    data = resp.json()

    assert "Verification Required" in data["title"]
    assert "holding bin" in data["recommendation_text"].lower()
    assert "bin-holding" in data["supporting_data"]["bin_ids"]
    assert data["supporting_data"]["pending_count"] == 2


def test_critical_occupancy_recommendation(client, test_db, sample_scan):
    """Verifies that high bin occupancy (>= 90%) triggers an urgent collection recommendation."""
    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    plastic_bin.current_inventory = 95.0
    plastic_bin.capacity = 100.0
    test_db.commit()

    resp = client.post("/api/recommendations/generate", json={"force_refresh": True})
    assert resp.status_code == 201
    data = resp.json()

    assert "Urgent" in data["title"]
    assert "Nearing Maximum Capacity" in data["title"]
    assert "bin-plastic" in data["supporting_data"]["bin_ids"]


def test_llm_output_validation_rejects_hallucinations(test_db):
    """
    Verifies that if an LLM hallucinates an unknown bin ID,
    the output validation rejects it and falls back to deterministic logic.
    """
    # Bad LLM generator citing an invented bin
    def hallucinating_llm(context):
        return {
            "title": "Inventory Advice",
            "text": "Transfer items from bin-plastic to bin-uranium immediately.",
            "supporting_data": {},
        }

    rec = generate_recommendation(
        db=test_db,
        force_refresh=True,
        client_id="test_validator_client",
        llm_generator=hallucinating_llm,
    )
    # Must reject and use deterministic fallback
    assert rec.generation_method == "deterministic_fallback"
    assert "bin-uranium" not in rec.recommendation_text


def test_llm_output_validation_accepts_valid_citation(test_db):
    """Verifies that a valid LLM response citing existing bins is accepted."""
    def valid_llm(context):
        return {
            "title": "Optimized Routing Suggestion",
            "text": "Inventory in bin-plastic and bin-glass is well balanced.",
            "supporting_data": {"source": "mock_llm"},
        }

    rec = generate_recommendation(
        db=test_db,
        force_refresh=True,
        client_id="test_validator_client_2",
        llm_generator=valid_llm,
    )
    assert rec.generation_method == "llm"
    assert rec.title == "Optimized Routing Suggestion"


def test_recommendation_lifecycle_status(client, test_db):
    """Verifies transitions across lifecycle states: new -> acknowledged -> resolved."""
    gen_resp = client.post("/api/recommendations/generate")
    rec_id = gen_resp.json()["id"]

    # Acknowledge
    ack_resp = client.patch(f"/api/recommendations/{rec_id}/status", json={"status": "acknowledged"})
    assert ack_resp.status_code == 200
    assert ack_resp.json()["status"] == "acknowledged"

    # Resolve
    res_resp = client.patch(f"/api/recommendations/{rec_id}/status", json={"status": "resolved"})
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "resolved"

    # Invalid status returns 422
    inv_resp = client.patch(f"/api/recommendations/{rec_id}/status", json={"status": "discarded_invalid"})
    assert inv_resp.status_code == 422


def test_grounded_qa_endpoint(client, test_db, sample_scan):
    """Verifies /api/recommendations/ask answers correctly from real database state."""
    # Confirm 20 items in plastic
    client.post(
        "/api/materials/confirm",
        json={"scan_id": sample_scan.id, "confirmed_category": "plastic", "quantity": 20.0},
    )

    resp = client.post(
        "/api/recommendations/ask",
        json={"question": "Which bin has the highest inventory?"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert "highest" in data["question"].lower()
    assert "Plastic Recycling" in data["answer"]
    assert "20.0" in data["answer"] or "20" in data["answer"]


def test_rate_limiting_enforcement(client):
    """Verifies that exceeding RATE_LIMIT_MAX_REQUESTS triggers 429 Too Many Requests."""
    reset_rate_limits()

    # Exhaust quota
    for i in range(RATE_LIMIT_MAX_REQUESTS):
        resp = client.post("/api/recommendations/generate", json={"force_refresh": True})
        assert resp.status_code == 201

    # Next request must be rate limited
    limit_resp = client.post("/api/recommendations/generate", json={"force_refresh": True})
    assert limit_resp.status_code == 429
    assert "rate limit exceeded" in limit_resp.json()["detail"].lower()
    assert "Retry-After" in limit_resp.headers
