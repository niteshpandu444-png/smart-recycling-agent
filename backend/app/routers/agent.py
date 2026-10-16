"""
Recycling Intelligence Agent Router.
Provides endpoints for sending inquiries to the agent and querying its operational status.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.adapters.schemas import (
    AgentMessageRequest,
    AgentMessageResponse,
    AgentStatusResponse,
)
from backend.app.services.agent_service import (
    get_agent_status,
    process_agent_message,
)

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.post(
    "/message",
    response_model=AgentMessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a message or query to the Recycling Intelligence Agent",
)
def post_agent_message(
    request: AgentMessageRequest,
    db: Session = Depends(get_db),
) -> AgentMessageResponse:
    """
    Submits a user query to the Recycling Intelligence Agent.
    When a GenAI provider is configured, the agent executes genuine read-only tool calls
    against current application state.
    When unconfigured, it uses deterministic fallback logic grounded in real database records.
    """
    return process_agent_message(db=db, request=request)


@router.get(
    "/status",
    response_model=AgentStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current operational status and capabilities of the Recycling Agent",
)
def get_agent_status_endpoint() -> AgentStatusResponse:
    """
    Reports whether live GenAI is active, provider configuration, and allowlisted tools.
    """
    return get_agent_status()
