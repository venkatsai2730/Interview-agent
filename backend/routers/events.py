"""Events router - migrated from main_legacy.py."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import Event as EventModel

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/")
async def list_events_endpoint(
    session_id: Optional[str] = None,
    type: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of pipeline events.

    Query params:
    - session_id: optional filter
    - type: optional filter (tts_fallback | stt_reconnect)
    - page: 1-based page number (default 1)
    - page_size: items per page (default 50)
    """
    filters = []
    if session_id is not None:
        filters.append(EventModel.session_id == session_id)
    if type is not None:
        filters.append(EventModel.type == type)

    count_stmt = select(func.count()).select_from(EventModel)
    if filters:
        count_stmt = count_stmt.where(*filters)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    rows_stmt = (
        select(EventModel)
        .order_by(EventModel.timestamp.desc())
        .offset(offset)
        .limit(page_size)
    )
    if filters:
        rows_stmt = rows_stmt.where(*filters)
    rows_result = await db.execute(rows_stmt)
    rows = rows_result.scalars().all()

    return {
        "items": [
            {
                "id": row.id,
                "type": row.type,
                "session_id": row.session_id,
                "timestamp": row.timestamp,
                "detail": row.detail,
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
