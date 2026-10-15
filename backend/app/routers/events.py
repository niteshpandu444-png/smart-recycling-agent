"""
Events Router.
Provides material flow audit history and compensating event reversal endpoints.
"""
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.adapters.schemas import (
    EventListResponse,
    MaterialEventResponse,
    EventReversalRequest,
)
from backend.app.services.digital_twin_service import get_filtered_events
from backend.app.services.material_service import (
    reverse_material_event,
    MaterialServiceError,
)

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get(
    "",
    response_model=EventListResponse,
    summary="Get timestamped material event history",
)
def get_events_endpoint(
    limit: int = Query(50, ge=1, le=200),
    cursor: Optional[str] = Query(None, description="Cursor for pagination (event ID)"),
    category: Optional[str] = Query(None, description="Filter by material category"),
    bin_id: Optional[str] = Query(None, description="Filter by source or destination bin ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    start_time: Optional[datetime] = Query(None, description="Filter events after timestamp"),
    end_time: Optional[datetime] = Query(None, description="Filter events before timestamp"),
    db: Session = Depends(get_db),
):
    """
    Returns immutable event audit records with filtering and cursor pagination.
    """
    items, next_cursor, total_count = get_filtered_events(
        db=db,
        limit=limit,
        cursor=cursor,
        category=category,
        bin_id=bin_id,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
    )
    return EventListResponse(
        items=items,
        next_cursor=next_cursor,
        total_count=total_count,
    )


@router.post(
    "/{event_id}/reverse",
    response_model=MaterialEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create compensating reversal event",
)
def reverse_event_endpoint(
    event_id: str,
    request: Optional[EventReversalRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Creates a compensating reversal event, restoring inventory without deleting records.
    """
    reason = request.reason if request else None
    try:
        rev_event = reverse_material_event(db, event_id=event_id, reason=reason)
        return rev_event
    except MaterialServiceError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
