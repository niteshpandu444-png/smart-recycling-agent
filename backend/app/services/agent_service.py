"""
Recycling Intelligence Agent Service.
Orchestrates genuine tool-calling LLM execution when configured,
with a robust, grounded deterministic fallback when credentials or provider are absent.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import httpx
from sqlalchemy.orm import Session

from backend.app.config import (
    get_agent_config,
    is_agent_configured,
)
from backend.app.adapters.schemas import (
    AgentMessageRequest,
    AgentMessageResponse,
    AgentStatusResponse,
    ToolEvidence,
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

logger = logging.getLogger("smart_recycling.agent_service")

SYSTEM_PROMPT = """You are the Recycling Intelligence Agent for the Smart Recycling facility.
You assist human facility operators by answering practical operational questions strictly grounded in real database records.

AVAILABLE TOOLS:
1. get_digital_twin_snapshot: Overall system snapshot, confirmed totals, bin occupancies, holding count, and batch metrics.
2. get_bin_status: Virtual bin occupancies, capacity thresholds, contamination risks, and status filters.
3. get_recent_events: Recent material confirmation, routing, emptying, or reclassification audit events.
4. get_batch_review_summary: Mixed-waste scene scans, detected item totals, and scans needing manual operator review.
5. get_material_guidance: Recycling policies, destination bins, look-alike confusable pairs, and hazardous handling.

STRICT OPERATIONAL RULES:
1. Always ground your answers in actual tool results. If you need data, call the relevant tool first.
2. Never invent bin capacities, item counts, material classifications, or facility procedures. If data is not recorded, state that clearly.
3. Clearly distinguish between:
   - Observed facts (e.g. 'Bin bin-plastic is at 85% occupancy with 42.5 items')
   - Deterministic recycling rules (e.g. 'Batteries are hazardous and must be placed in specialized collection')
   - Model inference or detector uncertainty (e.g. 'Item 2 was sequestered for review due to low confidence 0.48')
4. You are strictly advisory in v1. You CANNOT confirm items, alter inventory, change bin thresholds, or mutate the database. Explain recommended actions for the human operator to take.
5. Direct hazardous, unknown, or ambiguous items to manual review and holding bins, never to curbside recycling.
"""


def _sanitize_error_message(error_str: str) -> str:
    """Removes sensitive keys or tokens from error strings before logging or returning."""
    cfg = get_agent_config()
    api_key = cfg.get("api_key")
    if api_key and api_key in error_str:
        return error_str.replace(api_key, "[REDACTED_API_KEY]")
    return error_str


# ---------------------------------------------------------------------------
# Deterministic Fallback Engine
# ---------------------------------------------------------------------------

def _run_deterministic_fallback(
    db: Session,
    message: str,
    reason: Optional[str] = None,
) -> AgentMessageResponse:
    """
    Computes grounded operational answers using the same allowlisted tools when
    the LLM provider is disabled, unconfigured, or unreachable.
    Never invents data; clearly distinguishes facts from recommendations.
    """
    q_lower = message.lower().strip()
    evidence_list: List[ToolEvidence] = []
    supporting_facts: Dict[str, Any] = {}
    recommended_action: Optional[str] = None
    answer_parts: List[str] = []

    if reason:
        prefix_note = f"*[Deterministic Fallback Mode — {reason}]*\n\n"
    else:
        prefix_note = "*[Deterministic Fallback Mode — GenAI provider unconfigured]*\n\n"

    # Intent 1: Bin Capacity / Fullest Bins / Overflow
    if any(k in q_lower for k in ("capacity", "fullest", "overflow", "approaching", "nearing", "bin status", "which bin", "bins")):
        data, summary = tool_get_bin_status(db, GetBinStatusArgs())
        evidence_list.append(ToolEvidence(
            tool_name="get_bin_status",
            arguments={},
            summary=summary,
            result_preview={"count": data["count"]},
        ))
        bins = data.get("bins", [])
        critical_bins = [b for b in bins if b.get("is_critical")]
        warning_bins = [b for b in bins if b.get("is_nearing_capacity") and not b.get("is_critical")]

        supporting_facts["critical_bins"] = critical_bins
        supporting_facts["warning_bins"] = warning_bins

        answer_parts.append("### Virtual Bin Capacity Status")
        if critical_bins:
            answer_parts.append("\n**Critical Bins (>= 90% capacity):**")
            for b in critical_bins:
                answer_parts.append(
                    f"- **{b['name']}** (`{b['id']}`): **{b['occupancy_percentage']}%** full "
                    f"({b['current_inventory']:.1f} / {b['capacity']:.1f} {b.get('inventory_unit', 'items')}). "
                    f"Contamination risk: {b['contamination_risk']*100:.1f}%."
                )
            recommended_action = f"Empty or schedule collection for {critical_bins[0]['name']} immediately to prevent overflow."
        elif warning_bins:
            answer_parts.append("\n**Warning Bins (>= 75% capacity):**")
            for b in warning_bins:
                answer_parts.append(
                    f"- **{b['name']}** (`{b['id']}`): **{b['occupancy_percentage']}%** full "
                    f"({b['current_inventory']:.1f} / {b['capacity']:.1f} {b.get('inventory_unit', 'items')})."
                )
            recommended_action = f"Monitor incoming flows into {warning_bins[0]['name']} and prepare overflow staging."
        else:
            answer_parts.append("\nAll virtual bins are currently within normal capacity thresholds (< 75%).")
            if bins:
                highest = max(bins, key=lambda x: x.get("occupancy_percentage", 0.0))
                answer_parts.append(
                    f"The highest occupancy bin is **{highest['name']}** at {highest['occupancy_percentage']}% "
                    f"({highest['current_inventory']:.1f}/{highest['capacity']:.1f} items)."
                )
            recommended_action = "Continue regular sorting operations; no bin emptying required at this time."

    # Intent 2: Recent Confirmed Materials / Events Audit
    elif any(k in q_lower for k in ("recent", "confirmed", "events", "audit", "history", "what material")):
        data, summary = tool_get_recent_events(db, GetRecentEventsArgs(limit=10, event_type="confirmed"))
        evidence_list.append(ToolEvidence(
            tool_name="get_recent_events",
            arguments={"limit": 10, "event_type": "confirmed"},
            summary=summary,
            result_preview={"returned_count": data["returned_count"]},
        ))
        events = data.get("events", [])
        supporting_facts["recent_events_count"] = len(events)

        answer_parts.append("### Recently Confirmed Materials")
        if events:
            # Group by category
            cat_counts: Dict[str, float] = {}
            for ev in events:
                c = ev["affected_category"]
                cat_counts[c] = cat_counts.get(c, 0.0) + ev["quantity"]

            answer_parts.append("Recent confirmed flow totals by category:")
            for cat, qty in sorted(cat_counts.items()):
                answer_parts.append(f"- **{cat.title()}**: {qty:.1f} item(s)")

            answer_parts.append(f"\nMost recent event: `{events[0]['affected_category']}` ({events[0]['quantity']} item) at {events[0]['timestamp']}.")
            recommended_action = "Review recent events against incoming batch expectations."
        else:
            answer_parts.append("No confirmed material events recorded recently in database history.")
            recommended_action = "Await operator confirmations from the scanner or batch review panel."

    # Intent 3: Batch Review Items / Mixed-Waste Scans
    elif any(k in q_lower for k in ("batch", "review", "manual review", "scene", "mixed waste", "unconfirmed")):
        data, summary = tool_get_batch_review_summary(db, GetBatchReviewSummaryArgs(limit=5))
        evidence_list.append(ToolEvidence(
            tool_name="get_batch_review_summary",
            arguments={"limit": 5},
            summary=summary,
            result_preview={"pending_review_count": data["pending_review_count"]},
        ))
        pending_scans = data.get("pending_review_scans", [])
        batches = data.get("recent_batches", [])
        supporting_facts["pending_review_count"] = len(pending_scans)

        answer_parts.append("### Mixed-Waste Batch Review Status")
        answer_parts.append(f"- Total recent batches sampled: **{len(batches)}**")
        answer_parts.append(f"- Items detected across sample: **{data.get('total_detected_in_sample', 0)}**")
        answer_parts.append(f"- Items flagged for operator review: **{data.get('total_review_required_in_sample', 0)}**")

        if pending_scans:
            answer_parts.append("\n**Items Actively Requiring Manual Review:**")
            for ps in pending_scans[:5]:
                margin_str = f", margin {ps['margin']:.2f}" if ps.get("margin") is not None else ""
                answer_parts.append(
                    f"- Scan `{ps['scan_id'][:8]}...`: Predicted **{ps['predicted_category']}** "
                    f"(confidence {ps['confidence']:.2f}{margin_str})"
                )
            recommended_action = "Inspect flagged batch items in the Batch Review panel to confirm or reclassify before inventory ingestion."
        else:
            answer_parts.append("\nNo batch items are currently waiting in the review queue.")
            recommended_action = "Run new mixed-waste scene scans or review single-item scans."

    # Intent 4: Why review is needed / Ambiguity criteria
    elif any(k in q_lower for k in ("why", "ambiguity", "reason", "criteria", "rule")):
        answer_parts.append("### Material Review Criteria")
        answer_parts.append(
            "Detected items require manual operator review when any of the following conservative safety triggers fire:\n"
            "1. **Low Detection Confidence**: Detector comparison score is below 0.50.\n"
            "2. **Confusable Material Pair**: Top predictions form a registered look-alike group "
            "(e.g. Paper ↔ Plastic, Compostable ↔ Plastic) with a score margin below 0.15.\n"
            "3. **Multi-Material Region Conflict**: Detector returned multiple contradictory material classes for the same object box.\n"
            "4. **Cross-Check Disagreement**: The secondary whole-image crop classifier disagrees with the object detector.\n"
            "5. **Featureless Crop**: Standard deviation of crop texture is below threshold (< 8.0), indicating an uninformative patch.\n"
            "6. **Hazardous / Unsupported Class**: Item classified as battery, biological, or generic trash requiring specialized handling."
        )
        recommended_action = "Always examine resin codes, lining indicators, or labels when reviewing flagged items."

    # Intent 5: Operator Prioritization / What to do next
    elif any(k in q_lower for k in ("prioritize", "priority", "next", "what should", "action", "recommend")):
        snap_data, snap_summary = tool_get_digital_twin_snapshot(db, GetDigitalTwinSnapshotArgs())
        evidence_list.append(ToolEvidence(
            tool_name="get_digital_twin_snapshot",
            arguments={},
            summary=snap_summary,
            result_preview={"confirmed": snap_data["total_confirmed_items"]},
        ))
        bins = snap_data.get("bins", [])
        critical = [b for b in bins if b.get("occupancy_percentage") and b["occupancy_percentage"] >= 90.0]
        warning = [b for b in bins if b.get("occupancy_percentage") and b["occupancy_percentage"] >= 75.0 and b["occupancy_percentage"] < 90.0]
        pending_holding = snap_data.get("pending_verification_count", 0)
        pending_review = snap_data.get("needs_review_scan_count", 0)

        answer_parts.append("### Operator Action Priorities")
        priorities = []
        if critical:
            priorities.append(f"1. **URGENT**: Empty bin **{critical[0]['name']}** ({critical[0]['occupancy_percentage']}% full) to avoid system overflow.")
        if pending_holding > 0:
            priorities.append(f"2. **VERIFICATION**: Re-evaluate {pending_holding} ambiguous item(s) sequestered in the holding bin.")
        if warning:
            priorities.append(f"3. **MONITORING**: Stage secondary sorting bins for **{warning[0]['name']}** ({warning[0]['occupancy_percentage']}% full).")
        if pending_review > 0:
            priorities.append(f"4. **BATCH REVIEW**: Resolve {pending_review} pending mixed-waste scan(s) in the review queue.")

        if not priorities:
            priorities.append("1. **NORMAL OPERATIONS**: All bins are below 75% capacity and no items are pending review. System flow is stable.")

        answer_parts.extend(priorities)
        recommended_action = priorities[0].split("**")[1] if "**" in priorities[0] else "Continue steady-state sorting."

    # Intent 6: Material Guidance
    else:
        # Check if query matches a known material name
        candidate_categories = ["plastic", "paper", "metal", "glass", "battery", "biological", "organic", "hazardous", "trash", "reusable", "compostable"]
        matched_category = None
        for cat in candidate_categories:
            if cat in q_lower:
                matched_category = cat
                break

        if matched_category:
            guidance_data, summary = tool_get_material_guidance(db, GetMaterialGuidanceArgs(category=matched_category))
            evidence_list.append(ToolEvidence(
                tool_name="get_material_guidance",
                arguments={"category": matched_category},
                summary=summary,
                result_preview={"destination_bin_id": guidance_data["destination_bin_id"]},
            ))
            supporting_facts["guidance"] = guidance_data

            answer_parts.append(f"### Material Guidance: {guidance_data['display_name']}")
            answer_parts.append(f"- **Target Destination**: `{guidance_data['destination_bin_id']}`")
            answer_parts.append(f"- **Classification Group**: {guidance_data['classification_group']}")
            answer_parts.append(f"- **Curbside Accepted**: {'Yes' if guidance_data['curbside_accepted'] else 'No / Specialized Handling'}")
            answer_parts.append(f"- **Guidance**: {guidance_data['guidance']}")

            if guidance_data.get("confusable_with"):
                answer_parts.append(f"- **Confusable Look-Alikes**: {', '.join(guidance_data['confusable_with'])}")

            if guidance_data.get("is_hazardous"):
                recommended_action = f"Route {matched_category} to authorized hazardous handling facility; do NOT place in standard recycling bins."
            else:
                recommended_action = f"Route clean items to {guidance_data['destination_bin_id']}."
        else:
            # General system summary
            snap_data, snap_summary = tool_get_digital_twin_snapshot(db, GetDigitalTwinSnapshotArgs())
            evidence_list.append(ToolEvidence(
                tool_name="get_digital_twin_snapshot",
                arguments={},
                summary=snap_summary,
                result_preview={"confirmed": snap_data["total_confirmed_items"]},
            ))
            answer_parts.append("### Digital Twin Facility Status")
            answer_parts.append(
                f"- Total Confirmed Items in Inventory: **{snap_data['total_confirmed_items']:.0f}**\n"
                f"- Virtual Bins Tracked: **{len(snap_data['bins'])}**\n"
                f"- Ambiguous Items in Holding Bin: **{snap_data['pending_verification_count']}**\n"
                f"- Mixed-Waste Scans Needing Review: **{snap_data.get('needs_review_scan_count', 0)}**"
            )
            recommended_action = "Ask about bin capacity, recent confirmed materials, batch reviews, or material guidance."

    full_answer = prefix_note + "\n".join(answer_parts)

    return AgentMessageResponse(
        agent_mode="deterministic_fallback",
        answer=full_answer,
        is_fallback=True,
        tool_calls=evidence_list,
        recommended_action=recommended_action,
        supporting_facts=supporting_facts,
        model_identifier="deterministic_rules_engine",
        timestamp=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Tool-Using GenAI Agent Execution (OpenAI Compatible)
# ---------------------------------------------------------------------------

def _run_tool_using_agent(
    db: Session,
    user_message: str,
    conversation_id: Optional[str] = None,
) -> AgentMessageResponse:
    """
    Executes a multi-turn tool-calling conversation with the configured LLM endpoint.
    Maintains bounded loop, strict tool allowlisting, and safety validations.
    """
    cfg = get_agent_config()
    if not cfg["is_configured"]:
        return _run_deterministic_fallback(db, user_message, reason="LLM provider unconfigured")

    endpoint = f"{cfg['base_url']}/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }

    tools_spec = get_openai_tool_definitions()
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    evidence_records: List[ToolEvidence] = []
    rounds = 0
    max_rounds = cfg["max_tool_rounds"]
    timeout_secs = cfg["timeout_seconds"]

    client = httpx.Client(timeout=timeout_secs)

    try:
        while rounds < max_rounds:
            rounds += 1
            payload = {
                "model": cfg["model"],
                "messages": messages,
                "tools": tools_spec,
                "tool_choice": "auto",
                "temperature": 0.2,
            }

            try:
                response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                res_json = response.json()
            except httpx.TimeoutException:
                logger.warning("LLM request timed out after %s seconds. Falling back to deterministic logic.", timeout_secs)
                return _run_deterministic_fallback(db, user_message, reason=f"Provider timed out ({timeout_secs}s)")
            except httpx.HTTPStatusError as http_err:
                sanitized_msg = _sanitize_error_message(str(http_err))
                logger.warning("LLM endpoint returned HTTP error %s: %s", http_err.response.status_code, sanitized_msg)
                return _run_deterministic_fallback(db, user_message, reason=f"Provider HTTP {http_err.response.status_code}")
            except Exception as exc:
                sanitized_msg = _sanitize_error_message(str(exc))
                logger.warning("LLM connection failed: %s", sanitized_msg)
                return _run_deterministic_fallback(db, user_message, reason="Provider connection error")

            choices = res_json.get("choices", [])
            if not choices or not isinstance(choices, list):
                logger.warning("LLM returned malformed choices list.")
                return _run_deterministic_fallback(db, user_message, reason="Malformed provider response")

            msg = choices[0].get("message", {})
            tool_calls = msg.get("tool_calls")

            # Append the assistant's message to the conversation history
            messages.append(msg)

            # If no tool calls requested, we have reached the final answer
            if not tool_calls:
                final_content = msg.get("content", "") or "No response generated."
                return AgentMessageResponse(
                    agent_mode="live_llm",
                    answer=final_content,
                    is_fallback=False,
                    tool_calls=evidence_records,
                    recommended_action=_extract_recommended_action(final_content),
                    supporting_facts={"tool_rounds": rounds},
                    model_identifier=cfg["model"],
                    timestamp=datetime.now(timezone.utc),
                )

            # Process every requested tool call
            for tc in tool_calls:
                call_id = tc.get("id", "call_default")
                fn_info = tc.get("function", {})
                fn_name = fn_info.get("name", "")
                raw_args = fn_info.get("arguments", "{}")

                try:
                    tool_result, tool_summary = execute_allowlisted_tool(fn_name, raw_args, db)
                    evidence_records.append(ToolEvidence(
                        tool_name=fn_name,
                        arguments=raw_args if isinstance(raw_args, dict) else json.loads(raw_args or "{}"),
                        summary=tool_summary,
                        result_preview={"status": "ok"},
                    ))
                    tool_content = json.dumps(tool_result)
                except UnknownToolError as unk:
                    logger.warning("LLM requested unknown tool '%s'", fn_name)
                    tool_content = json.dumps({"error": str(unk)})
                except InvalidToolArgsError as inv:
                    logger.warning("LLM provided invalid arguments for tool '%s': %s", fn_name, inv.errors)
                    tool_content = json.dumps({"error": str(inv)})
                except Exception as exc:
                    logger.exception("Tool execution of '%s' failed unexpectedly", fn_name)
                    tool_content = json.dumps({"error": f"Tool execution failed: {type(exc).__name__}"})

                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": tool_content,
                })

        # Bounded loop reached max rounds
        logger.info("Agent tool loop reached maximum rounds (%s). Requesting final summary.", max_rounds)
        messages.append({
            "role": "user",
            "content": "Please synthesize your final answer and recommendation based on the tool results gathered so far.",
        })
        try:
            summary_res = client.post(
                endpoint,
                headers=headers,
                json={"model": cfg["model"], "messages": messages, "temperature": 0.2},
            )
            final_text = summary_res.json()["choices"][0]["message"]["content"]
            return AgentMessageResponse(
                agent_mode="live_llm",
                answer=final_text,
                is_fallback=False,
                tool_calls=evidence_records,
                recommended_action=_extract_recommended_action(final_text),
                supporting_facts={"tool_rounds": rounds, "hit_max_rounds": True},
                model_identifier=cfg["model"],
                timestamp=datetime.now(timezone.utc),
            )
        except Exception:
            return _run_deterministic_fallback(db, user_message, reason="Tool loop exceeded bound")
    finally:
        client.close()


def _extract_recommended_action(text: str) -> Optional[str]:
    """Heuristic extraction of recommended action from model output."""
    match = re.search(r"(?:Action recommended|Recommended action|Next action|Action):\s*([^\n\.]+[\.])", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Public Service Entrypoints
# ---------------------------------------------------------------------------

def process_agent_message(
    db: Session,
    request: AgentMessageRequest,
) -> AgentMessageResponse:
    """
    Main entry point for user inquiries to the Recycling Intelligence Agent.
    If the provider is configured and enabled, executes genuine tool-calling LLM.
    Otherwise, executes the grounded deterministic fallback.
    """
    if is_agent_configured():
        return _run_tool_using_agent(db, request.message, request.conversation_id)
    return _run_deterministic_fallback(db, request.message)


def get_agent_status() -> AgentStatusResponse:
    """Returns current status and capabilities of the Recycling Intelligence Agent."""
    config = get_agent_config()
    configured = config["is_configured"]
    return AgentStatusResponse(
        enabled=config["enabled"],
        agent_mode="live_llm" if configured else "deterministic_fallback",
        provider_configured=configured,
        model=config["model"] if configured else None,
        base_url=config["base_url"] if configured else None,
        available_tools=sorted(list(ALLOWLISTED_TOOLS.keys())),
    )
