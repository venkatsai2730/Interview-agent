"""Reports router - migrated from main_legacy.py."""

from datetime import date, datetime, timedelta, timezone
from typing import Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import get_db
from backend.models import Report as ReportModel, Session as SessionModel

router = APIRouter(prefix="/reports", tags=["reports"])


class ReportListItem(BaseModel):
    """Report list item schema."""
    session_id: str
    skill_pack_name: Optional[str]
    template: str
    generated_at: datetime
    recommendation: Optional[str]

    class Config:
        from_attributes = True


class ReportListResponse(BaseModel):
    """Report list response schema."""
    items: List[ReportListItem]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=ReportListResponse)
async def list_reports_endpoint(
    template: Optional[str] = None,
    channel: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """Return a paginated list of reports with optional filters.

    Query params:
    - template: optional filter (scorecard | discovery-brief | audit-log | coaching-report)
    - channel: optional filter (teams | phone)
    - from_date: optional ISO date string (inclusive)
    - to_date: optional ISO date string (inclusive)
    - page: 1-based page number (default 1)
    - page_size: items per page (default 20)
    """
    filters = []
    if template is not None:
        filters.append(ReportModel.template == template)
    if channel is not None:
        filters.append(SessionModel.channel == channel)
    if from_date is not None:
        try:
            dt_from = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
            filters.append(ReportModel.generated_at >= dt_from)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date format; use ISO date (YYYY-MM-DD)")
    if to_date is not None:
        try:
            dt_to = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
            dt_to = dt_to + timedelta(days=1)
            filters.append(ReportModel.generated_at < dt_to)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date format; use ISO date (YYYY-MM-DD)")

    # Total count (with session join if channel filter is used)
    if channel is not None:
        count_stmt = (
            select(func.count())
            .select_from(ReportModel)
            .join(SessionModel, ReportModel.session_id == SessionModel.session_id)
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
    else:
        count_stmt = select(func.count()).select_from(ReportModel)
        if filters:
            count_stmt = count_stmt.where(*filters)
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Paginated rows joined with sessions for skill_pack_name
    offset = (page - 1) * page_size
    rows_stmt = (
        select(ReportModel, SessionModel.skill_pack)
        .join(SessionModel, ReportModel.session_id == SessionModel.session_id, isouter=True)
        .order_by(ReportModel.generated_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    if filters:
        rows_stmt = rows_stmt.where(*filters)
    rows_result = await db.execute(rows_stmt)
    rows = rows_result.all()

    items = []
    for report_row, skill_pack in rows:
        skill_pack_name: Optional[str] = None
        try:
            skill_pack_name = (skill_pack or {}).get("skill", {}).get("name")
        except (AttributeError, TypeError):
            pass

        recommendation: Optional[str] = None
        try:
            recommendation = (report_row.content or {}).get("recommendation")
        except (AttributeError, TypeError):
            pass

        items.append({
            "session_id": report_row.session_id,
            "skill_pack_name": skill_pack_name,
            "template": report_row.template,
            "generated_at": report_row.generated_at,
            "recommendation": recommendation,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{session_id}")
async def get_report_endpoint(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return the full report content for a session."""
    result = await db.execute(
        select(ReportModel).where(ReportModel.session_id == session_id)
    )
    report_row = result.scalar_one_or_none()
    if report_row is None:
        raise HTTPException(status_code=404, detail="Report not found")

    return {
        "session_id": report_row.session_id,
        "template": report_row.template,
        "content": report_row.content,
        "generated_at": report_row.generated_at,
        "email_sent": report_row.email_sent,
        "chat_posted": report_row.chat_posted,
    }
