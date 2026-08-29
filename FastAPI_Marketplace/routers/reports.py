from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from bot import notify_admins_about_new_report
from dependencies import get_current_admin_user, get_current_user
from models import Comment, Product, Report, User
from schemas import AdminReportResponse, ReportCreate, ReportResponse, ReportStatusUpdate

router = APIRouter(prefix="/api/v1", tags=["reports"])

VALID_REPORT_REASONS = {
    "шахрайство",
    "спам / спам-акаунт",
    "спам",
    "невідповідність товару",
    "нецензурна лексика",
    "інше",
    "fraud",
    "spam",
    "misrepresentation",
    "profanity",
    "other",
}


def normalize_reason(reason: str) -> str:
    value = (reason or "").strip()
    if not value:
        return "Інше"
    lookup = value.lower()
    if lookup in {"fraud", "шахрайство"}:
        return "Шахрайство"
    if lookup in {"spam", "спам / спам-акаунт", "спам-акаунт"}:
        return "Спам / Спам-акаунт"
    if lookup in {"misrepresentation", "невідповідність товару"}:
        return "Невідповідність товару"
    if lookup in {"profanity", "нецензурна лексика"}:
        return "Нецензурна лексика"
    if lookup in {"other", "інше"}:
        return "Інше"
    return value


async def _ensure_report_target_exists(db: AsyncSession, payload: ReportCreate) -> None:
    if payload.reported_user_id is None and payload.product_id is None and payload.comment_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Потрібно вказати хоча б один об'єкт: reported_user_id, product_id або comment_id.",
        )

    if payload.reported_user_id is not None:
        user = await db.get(User, payload.reported_user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача, на якого скаржаться, не знайдено.")

    if payload.product_id is not None:
        product = await db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено.")

    if payload.comment_id is not None:
        comment = await db.get(Comment, payload.comment_id)
        if comment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Коментар не знайдено.")


async def _report_exists_for_same_target(db: AsyncSession, reporter_id: int, payload: ReportCreate) -> bool:
    stmt = select(Report).where(
        Report.reporter_id == reporter_id,
        Report.status == "pending",
    )

    if payload.reported_user_id is not None:
        stmt = stmt.where(Report.reported_user_id == payload.reported_user_id)
    if payload.product_id is not None:
        stmt = stmt.where(Report.product_id == payload.product_id)
    if payload.comment_id is not None:
        stmt = stmt.where(Report.comment_id == payload.comment_id)

    existing = (await db.execute(stmt)).scalars().first()
    return existing is not None


async def _build_report_response(db: AsyncSession, report: Report) -> ReportResponse:
    response = ReportResponse.model_validate(report)
    response.reason = normalize_reason(report.reason)
    return response


async def _build_admin_report_response(db: AsyncSession, report: Report) -> AdminReportResponse:
    reporter = await db.get(User, report.reporter_id)
    reported_user = await db.get(User, report.reported_user_id) if report.reported_user_id is not None else None
    product = await db.get(Product, report.product_id) if report.product_id is not None else None
    comment = await db.get(Comment, report.comment_id) if report.comment_id is not None else None

    if report.reported_user_id is not None:
        target_type = "user"
        target_label = f"Користувач {reported_user.username if reported_user else report.reported_user_id}"
    elif report.product_id is not None:
        target_type = "product"
        target_label = f"Товар {product.title if product else report.product_id}"
    elif report.comment_id is not None:
        target_type = "comment"
        target_label = f"Коментар {comment.id if comment else report.comment_id}"
    else:
        target_type = "unknown"
        target_label = "Не вказано"

    return AdminReportResponse(
        id=report.id,
        reporter_id=report.reporter_id,
        reporter_name=reporter.username if reporter else None,
        reporter_email=reporter.email if reporter else None,
        reported_user_id=report.reported_user_id,
        reported_user_name=reported_user.username if reported_user else None,
        reported_user_email=reported_user.email if reported_user else None,
        product_id=report.product_id,
        product_title=product.title if product else None,
        comment_id=report.comment_id,
        comment_body=comment.body if comment else None,
        reason=normalize_reason(report.reason),
        details=report.details,
        status=report.status,
        created_at=report.created_at,
        target_type=target_type,
        target_label=target_label,
    )


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_report_target_exists(db, payload)

    if await _report_exists_for_same_target(db, current_user.id, payload):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ви вже подали скаргу в статусі pending на цей об'єкт.",
        )

    if payload.reason not in VALID_REPORT_REASONS and payload.reason.lower() not in {v.lower() for v in VALID_REPORT_REASONS}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Некоректна причина скарги.",
        )

    db_report = Report(
        reporter_id=current_user.id,
        reported_user_id=payload.reported_user_id,
        product_id=payload.product_id,
        comment_id=payload.comment_id,
        reason=normalize_reason(payload.reason),
        details=payload.details or payload.description,
        status="pending",
    )
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)

    await notify_admins_about_new_report(
        db_report.id,
        normalize_reason(payload.reason),
        current_user.display_name or current_user.username or current_user.email or "Користувач",
    )

    return await _build_report_response(db, db_report)


@router.get("/admin/reports", response_model=list[AdminReportResponse])
async def get_admin_reports(
    status: str = Query(default="all"),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_status = (status or "all").strip().lower()
    stmt = select(Report)

    if normalized_status != "all":
        if normalized_status not in {"pending", "resolved", "rejected"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некоректний статус фільтра.")
        stmt = stmt.where(Report.status == normalized_status)

    stmt = stmt.order_by(Report.created_at.desc())
    reports = (await db.execute(stmt)).scalars().all()
    return [await _build_admin_report_response(db, report) for report in reports]


@router.patch("/admin/reports/{report_id}/status", response_model=AdminReportResponse)
async def update_admin_report_status(
    report_id: int,
    payload: ReportStatusUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скаргу не знайдено.")

    report.status = payload.status
    await db.commit()
    await db.refresh(report)
    return await _build_admin_report_response(db, report)
