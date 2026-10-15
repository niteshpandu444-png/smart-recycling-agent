"""
Recommendations Router.
Provides endpoints for retrieving, generating, updating, and asking questions to recommendations.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.models import Recommendation
from backend.app.adapters.schemas import (
    RecommendationResponse,
    RecommendationGenerateRequest,
    RecommendationStatusUpdate,
    RecommendationAskRequest,
    RecommendationAskResponse,
)
from backend.app.services.recommendation_service import (
    generate_recommendation,
    answer_grounded_question,
    RateLimitExceededError,
)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("", response_model=List[RecommendationResponse], summary="List all generated recommendations")
def list_recommendations_endpoint(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status ('new', 'acknowledged', 'dismissed', 'resolved')"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(Recommendation)
    if status_filter:
        query = query.filter(Recommendation.status == status_filter.lower().strip())
    return query.order_by(Recommendation.created_at.desc()).limit(limit).all()


@router.post(
    "/generate",
    response_model=RecommendationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate contextual recommendation from current Digital Twin state",
)
def generate_recommendation_endpoint(
    http_request: Request,
    request: Optional[RecommendationGenerateRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Generates a recommendation grounded strictly in current application database state.
    Features:
    - Context hashing and caching (avoids duplicate calls when state hasn't changed)
    - Deterministic fallback when LLM is unavailable or fails validation
    - Evidence linking to specific bins and events
    - Rate limit enforcement with 429 response
    """
    client_ip = http_request.client.host if http_request.client else "unknown_client"
    force_refresh = request.force_refresh if request else False
    try:
        rec = generate_recommendation(
            db=db,
            force_refresh=force_refresh,
            client_id=client_ip,
        )
        return rec
    except RateLimitExceededError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)},
        )


@router.patch(
    "/{recommendation_id}/status",
    response_model=RecommendationResponse,
    summary="Update recommendation lifecycle status",
)
def update_recommendation_status_endpoint(
    recommendation_id: str,
    update: RecommendationStatusUpdate,
    db: Session = Depends(get_db),
):
    rec = db.query(Recommendation).filter(Recommendation.id == recommendation_id).first()
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recommendation '{recommendation_id}' not found.",
        )

    allowed = {"new", "acknowledged", "dismissed", "resolved"}
    st = update.status.lower().strip()
    if st not in allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{update.status}'. Allowed: {sorted(list(allowed))}",
        )

    rec.status = st
    db.commit()
    db.refresh(rec)
    return rec


@router.post(
    "/ask",
    response_model=RecommendationAskResponse,
    summary="Ask a grounded question answered strictly from database context",
)
def ask_recommendation_endpoint(
    request: RecommendationAskRequest,
    db: Session = Depends(get_db),
):
    """
    Answers natural language questions about facility inventory, bin filling, or ambiguity,
    strictly computed from real persisted application records.
    """
    return answer_grounded_question(db, question=request.question)
