"""
Focused test suite for Recycling Intelligence Agent v1.
Validates allowlisted tools, Pydantic argument schemas, unknown tool rejection,
bounded tool loop, provider timeout handling, credential safety, read-only guarantees,
and clean separation between live LLM and deterministic fallback.
"""
import json
from unittest.mock import MagicMock, patch
import pytest
import httpx
from sqlalchemy.orm import Session

from backend.app.models import (
    BatchScan,
    MaterialEntry,
    MaterialEvent,
    Scan,
    VirtualBin,
    generate_uuid,
    utc_now,
)
from backend.app.adapters.schemas import (
    AgentMessageRequest,
    AgentMessageResponse,
    AgentStatusResponse,
)
from backend.app.services.agent_tools import (
    ALLOWLISTED_TOOLS,
    GetBatchReviewSummaryArgs,
    GetBinStatusArgs,
    GetDigitalTwinSnapshotArgs,
    GetMaterialGuidanceArgs,
    GetRecentEventsArgs,
    InvalidToolArgsError,
    UnknownToolError,
    execute_allowlisted_tool,
    get_openai_tool_definitions,
    tool_get_batch_review_summary,
    tool_get_bin_status,
    tool_get_digital_twin_snapshot,
    tool_get_material_guidance,
    tool_get_recent_events,
)
from backend.app.services.agent_service import (
    _run_deterministic_fallback,
    _run_tool_using_agent,
    get_agent_status,
    process_agent_message,
)


def _configured_agent_config(**overrides):
    """Returns a complete, provider-ready test config without real credentials."""
    config = {
        "enabled": True,
        "base_url": "https://api.fake-llm.com/v1",
        "api_key": "sk-test-only-not-a-real-key",
        "model": "fake-test-model",
        "timeout_seconds": 5.0,
        "max_tool_rounds": 5,
        "is_configured": True,
    }
    config.update(overrides)
    return config


@pytest.fixture
def populated_db(test_db: Session) -> Session:
    """Populates an isolated test database with realistic bins, scans, events, and batches."""
    # 1. Virtual bins (one critical >=90%, one warning >=75%, one normal)
    plastic_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first()
    if plastic_bin:
        plastic_bin.capacity = 50.0
        plastic_bin.current_inventory = 46.0  # 46/50 = 92% (critical)
        plastic_bin.status = "warning"
    else:
        plastic_bin = VirtualBin(
            id="bin-plastic",
            name="Plastic Recycling",
            accepted_category="plastic",
            capacity=50.0,
            current_inventory=46.0,
            status="warning",
        )
        test_db.add(plastic_bin)

    paper_bin = test_db.query(VirtualBin).filter(VirtualBin.id == "bin-paper").first()
    if paper_bin:
        paper_bin.capacity = 50.0
        paper_bin.current_inventory = 39.0  # 39/50 = 78% (warning)
    else:
        paper_bin = VirtualBin(
            id="bin-paper",
            name="Paper & Cardboard",
            accepted_category="paper",
            capacity=50.0,
            current_inventory=39.0,
            status="normal",
        )
        test_db.add(paper_bin)

    # 2. Material Events
    ev1 = MaterialEvent(
        id="event-test-1",
        event_type="confirmed",
        quantity=3.0,
        unit="items",
        affected_category="plastic",
        destination_bin_id="bin-plastic",
        timestamp=utc_now(),
    )
    ev2 = MaterialEvent(
        id="event-test-2",
        event_type="confirmed",
        quantity=2.0,
        unit="items",
        affected_category="paper",
        destination_bin_id="bin-paper",
        timestamp=utc_now(),
    )
    test_db.add_all([ev1, ev2])

    # 3. Scans needing review
    scan1 = Scan(
        id="scan-review-1",
        predicted_category="paper",
        confidence=0.48,
        review_status="needs_review",
        margin=0.08,
        top_k_predictions=[{"category": "paper", "score": 0.48}, {"category": "plastic", "score": 0.40}],
    )
    scan2 = Scan(
        id="scan-review-2",
        predicted_category="plastic",
        confidence=0.35,
        review_status="needs_review",
        margin=0.02,
    )
    test_db.add_all([scan1, scan2])

    # 4. Batch scan
    batch = BatchScan(
        id="batch-test-1",
        detector_identifier="yolov8-mixed-waste",
        image_width=640,
        image_height=480,
        detection_count=4.0,
        review_required_count=2.0,
        category_totals={"paper": 2.0, "plastic": 2.0},
        item_scan_ids=["scan-review-1", "scan-review-2"],
    )
    test_db.add(batch)

    test_db.commit()
    return test_db


# ---------------------------------------------------------------------------
# 1. Allowlisted Tools Tests
# ---------------------------------------------------------------------------

def test_tool_get_digital_twin_snapshot(populated_db: Session):
    args = GetDigitalTwinSnapshotArgs()
    result, summary = tool_get_digital_twin_snapshot(populated_db, args)

    assert "bins" in result
    assert "total_confirmed_items" in result
    assert "category_inventory" in result
    assert "Digital Twin snapshot" in summary
    assert len(result["bins"]) >= 2


def test_tool_get_bin_status_all_and_filtered(populated_db: Session):
    # Test all bins
    all_res, all_sum = tool_get_bin_status(populated_db, GetBinStatusArgs())
    assert all_res["count"] >= 2
    assert "CRITICAL" in all_sum or "WARNING" in all_sum

    # Test filter by bin_id
    filtered_res, _ = tool_get_bin_status(populated_db, GetBinStatusArgs(bin_id="bin-plastic"))
    assert filtered_res["count"] == 1
    assert filtered_res["bins"][0]["id"] == "bin-plastic"
    assert filtered_res["bins"][0]["occupancy_percentage"] >= 90.0
    assert filtered_res["bins"][0]["is_critical"] is True

    # Test filter by min_occupancy_percentage
    high_occ_res, _ = tool_get_bin_status(populated_db, GetBinStatusArgs(min_occupancy_percentage=90.0))
    for b in high_occ_res["bins"]:
        assert b["occupancy_percentage"] >= 90.0


def test_tool_get_recent_events_with_filters(populated_db: Session):
    res, summary = tool_get_recent_events(populated_db, GetRecentEventsArgs(limit=5, event_type="confirmed"))
    assert res["returned_count"] >= 2
    for ev in res["events"]:
        assert ev["event_type"] == "confirmed"

    # Category filter
    plastic_events, _ = tool_get_recent_events(populated_db, GetRecentEventsArgs(category="plastic"))
    for ev in plastic_events["events"]:
        assert ev["affected_category"] == "plastic"


def test_tool_get_batch_review_summary(populated_db: Session):
    # Test general summary
    gen_res, gen_sum = tool_get_batch_review_summary(populated_db, GetBatchReviewSummaryArgs(limit=5))
    assert gen_res["batch_count"] >= 1
    assert gen_res["pending_review_count"] >= 2
    assert "detected items" in gen_sum

    # Test specific batch ID
    batch_res, batch_sum = tool_get_batch_review_summary(populated_db, GetBatchReviewSummaryArgs(batch_id="batch-test-1"))
    assert batch_res["batch_id"] == "batch-test-1"
    assert batch_res["detection_count"] == 4
    assert len(batch_res["items"]) == 2

    # Test non-existent batch
    missing_res, missing_sum = tool_get_batch_review_summary(populated_db, GetBatchReviewSummaryArgs(batch_id="non-existent"))
    assert "not found" in missing_sum


def test_tool_get_material_guidance(populated_db: Session):
    # Hazardous material
    battery_res, _ = tool_get_material_guidance(populated_db, GetMaterialGuidanceArgs(category="battery"))
    assert battery_res["is_hazardous"] is True
    assert battery_res["curbside_accepted"] is False
    assert battery_res["destination_bin_id"] == "bin-holding"

    # Standard recyclable
    plastic_res, _ = tool_get_material_guidance(populated_db, GetMaterialGuidanceArgs(category="plastic"))
    assert plastic_res["curbside_accepted"] is True
    assert plastic_res["destination_bin_id"] == "bin-plastic"
    assert "paper" in plastic_res["confusable_with"]


# ---------------------------------------------------------------------------
# 2. Argument Validation & Unknown Tool Handling
# ---------------------------------------------------------------------------

def test_execute_allowlisted_tool_valid_and_invalid(populated_db: Session):
    # Valid call with string JSON
    res, _ = execute_allowlisted_tool("get_bin_status", '{"min_occupancy_percentage": 75.0}', populated_db)
    assert "bins" in res

    # Unknown tool rejection
    with pytest.raises(UnknownToolError) as exc_info:
        execute_allowlisted_tool("drop_all_tables", {}, populated_db)
    assert "drop_all_tables" in str(exc_info.value)

    # Invalid arguments (limit exceeds 50)
    with pytest.raises(InvalidToolArgsError) as exc_info:
        execute_allowlisted_tool("get_recent_events", {"limit": 999}, populated_db)
    assert "limit" in str(exc_info.value)

    # Malformed JSON string
    with pytest.raises(InvalidToolArgsError) as exc_info:
        execute_allowlisted_tool("get_recent_events", "{not-valid-json", populated_db)
    assert "Malformed JSON" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. Read-Only Safety Guarantee
# ---------------------------------------------------------------------------

def test_tools_do_not_mutate_database(populated_db: Session):
    """Verifies that none of the allowlisted tools alters inventory or confirms materials."""
    before_entries = populated_db.query(MaterialEntry).count()
    before_events = populated_db.query(MaterialEvent).count()
    before_plastic_inv = populated_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory

    execute_allowlisted_tool("get_digital_twin_snapshot", {}, populated_db)
    execute_allowlisted_tool("get_bin_status", {}, populated_db)
    execute_allowlisted_tool("get_recent_events", {"limit": 10}, populated_db)
    execute_allowlisted_tool("get_batch_review_summary", {}, populated_db)
    execute_allowlisted_tool("get_material_guidance", {"category": "battery"}, populated_db)

    after_entries = populated_db.query(MaterialEntry).count()
    after_events = populated_db.query(MaterialEvent).count()
    after_plastic_inv = populated_db.query(VirtualBin).filter(VirtualBin.id == "bin-plastic").first().current_inventory

    assert before_entries == after_entries
    assert before_events == after_events
    assert before_plastic_inv == after_plastic_inv


# ---------------------------------------------------------------------------
# 4. Deterministic Fallback Engine
# ---------------------------------------------------------------------------

def test_deterministic_fallback_bins_query(populated_db: Session):
    req = AgentMessageRequest(message="Which bins are approaching their configured capacity?")
    res = process_agent_message(populated_db, req)

    assert res.is_fallback is True
    assert res.agent_mode == "deterministic_fallback"
    assert "Plastic" in res.answer
    assert "Critical Bins" in res.answer
    assert res.recommended_action is not None
    assert any(t.tool_name == "get_bin_status" for t in res.tool_calls)


def test_deterministic_fallback_recent_materials(populated_db: Session):
    req = AgentMessageRequest(message="What material types have recently been confirmed?")
    res = process_agent_message(populated_db, req)

    assert res.is_fallback is True
    assert "Recently Confirmed Materials" in res.answer
    assert "Plastic" in res.answer or "Paper" in res.answer
    assert any(t.tool_name == "get_recent_events" for t in res.tool_calls)


def test_deterministic_fallback_batch_items(populated_db: Session):
    req = AgentMessageRequest(message="Which batch items need manual review?")
    res = process_agent_message(populated_db, req)

    assert res.is_fallback is True
    assert "Mixed-Waste Batch Review Status" in res.answer
    assert any(t.tool_name == "get_batch_review_summary" for t in res.tool_calls)


def test_deterministic_fallback_prioritization(populated_db: Session):
    req = AgentMessageRequest(message="What should the operator prioritize next?")
    res = process_agent_message(populated_db, req)

    assert res.is_fallback is True
    assert "Operator Action Priorities" in res.answer
    assert "URGENT" in res.answer
    assert res.recommended_action is not None


# ---------------------------------------------------------------------------
# 5. LLM Tool-Calling Integration (Mocked)
# ---------------------------------------------------------------------------

def test_tool_calling_llm_execution_success(populated_db: Session):
    """Simulates a model calling get_bin_status, executing it, and returning final answer."""
    tool_call_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "type": "function",
                            "function": {
                                "name": "get_bin_status",
                                "arguments": '{"min_occupancy_percentage": 75.0}',
                            },
                        }
                    ],
                }
            }
        ]
    }

    final_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Plastic Bin is at 92% capacity and needs attention. Recommended action: Empty Plastic Bin.",
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_post = MagicMock()
    # First turn: returns tool_call; Second turn: returns final_response
    mock_post.side_effect = [
        MagicMock(status_code=200, json=lambda: tool_call_response, raise_for_status=lambda: None),
        MagicMock(status_code=200, json=lambda: final_response, raise_for_status=lambda: None),
    ]
    mock_client.post = mock_post

    with patch("backend.app.services.agent_service.get_agent_config", return_value=_configured_agent_config()), \
         patch("httpx.Client", return_value=mock_client):

        res = _run_tool_using_agent(populated_db, "Which bins are full?")

        assert res.agent_mode == "live_llm"
        assert res.is_fallback is False
        assert "Plastic Bin is at 92%" in res.answer
        assert len(res.tool_calls) == 1
        assert res.tool_calls[0].tool_name == "get_bin_status"
        assert res.recommended_action == "Empty Plastic Bin."


def test_tool_calling_bounded_loop(populated_db: Session):
    """Ensures tool calling does not run indefinitely if model keeps requesting tools."""
    infinite_tool_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_inf",
                            "type": "function",
                            "function": {"name": "get_digital_twin_snapshot", "arguments": "{}"},
                        }
                    ],
                }
            }
        ]
    }

    mock_client = MagicMock()
    mock_post = MagicMock()
    mock_post.return_value = MagicMock(
        status_code=200,
        json=lambda: infinite_tool_response,
        raise_for_status=lambda: None,
    )
    mock_client.post = mock_post

    with patch("backend.app.services.agent_service.get_agent_config", return_value=_configured_agent_config(max_tool_rounds=3)), \
         patch("httpx.Client", return_value=mock_client):

        res = _run_tool_using_agent(populated_db, "Check status")
        # Should gracefully stop and not hang
        assert res.is_fallback is True or res.supporting_facts.get("hit_max_rounds") is True


def test_provider_timeout_falls_back_gracefully(populated_db: Session):
    """Ensures provider timeouts fall back to deterministic responses without failing with 500."""
    mock_client = MagicMock()
    mock_client.post.side_effect = httpx.TimeoutException("Connection timed out")

    with patch("backend.app.services.agent_service.get_agent_config", return_value=_configured_agent_config()), \
         patch("httpx.Client", return_value=mock_client):

        res = _run_tool_using_agent(populated_db, "Which bins are full?")
        assert res.is_fallback is True
        assert res.agent_mode == "deterministic_fallback"
        assert "Plastic" in res.answer


def test_provider_error_does_not_leak_api_key(populated_db: Session):
    """Ensures provider exceptions do not expose the API key in the response."""
    secret_key = "sk-test-only-secret-key"
    mock_client = MagicMock()
    mock_client.post.side_effect = Exception(f"Failed to connect with Authorization: Bearer {secret_key}")

    with patch("backend.app.services.agent_service.get_agent_config", return_value=_configured_agent_config(api_key=secret_key)), \
         patch("httpx.Client", return_value=mock_client):

        res = _run_tool_using_agent(populated_db, "Which bins are full?")
        assert secret_key not in res.answer
        assert res.is_fallback is True


# ---------------------------------------------------------------------------
# 6. API Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_agent_status_endpoint(client):
    res = client.get("/api/agent/status")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "agent_mode" in data
    assert "available_tools" in data
    assert "get_digital_twin_snapshot" in data["available_tools"]
    assert "get_bin_status" in data["available_tools"]


def test_agent_status_uses_effective_dynamic_configuration():
    configured = _configured_agent_config()
    with patch("backend.app.services.agent_service.get_agent_config", return_value=configured):
        status = get_agent_status()

    assert status.enabled is True
    assert status.provider_configured is True
    assert status.agent_mode == "live_llm"
    assert status.model == configured["model"]
    assert status.base_url == configured["base_url"]

    unconfigured = _configured_agent_config(enabled=False, is_configured=False)
    with patch("backend.app.services.agent_service.get_agent_config", return_value=unconfigured):
        status = get_agent_status()

    assert status.enabled is False
    assert status.provider_configured is False
    assert status.agent_mode == "deterministic_fallback"
    assert status.model is None
    assert status.base_url is None


def test_api_agent_message_endpoint(client, populated_db: Session):
    res = client.post(
        "/api/agent/message",
        json={"message": "Which bins are approaching capacity?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["agent_mode"] in ("live_llm", "deterministic_fallback")
    assert "answer" in data
    assert "tool_calls" in data
    assert isinstance(data["tool_calls"], list)
