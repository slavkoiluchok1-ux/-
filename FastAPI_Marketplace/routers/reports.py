from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot import send_message
from database import async_session, get_db
from dependencies import get_current_user
from models import Product, Report, Review, User
from schemas import ReportCreate, ReportResponse

router = APIRouter(prefix="/api/v1", tags=["reports"])


async def notify_admins_about_new_report(report_id: int) -> None:
    async with async_session() as session:
        admins = (
            await session.execute(
                select(User).where(or_(User.is_admin.is_(True), User.is_superuser.is_(True)))
            )
        ).scalars().all()

    for admin in admins:
        if admin.telegram_chat_id:
            await send_message(
                admin.telegram_chat_id,
                (
                    f"🚩 Нова скарга #{report_id}\n"
                    "Перейдіть до адмін-панелі для розгляду."
                ),
            )


@router.post("/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target_fields = [payload.reported_user_id, payload.product_id, payload.comment_id]
    if all(value is None for value in target_fields):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Хоча б одне з полів reported_user_id, product_id або comment_id має бути заповнене.",
        )

    target_checks = []
    if payload.reported_user_id is not None:
        target_checks.append(("user", payload.reported_user_id))
    if payload.product_id is not None:
        target_checks.append(("product", payload.product_id))
    if payload.comment_id is not None:
        target_checks.append(("comment", payload.comment_id))

    for kind, target_id in target_checks:
        if kind == "user":
            user = await db.get(User, target_id)
            if user is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено.")
            if user.id == current_user.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ви не можете подати скаргу на самого себе.")
        elif kind == "product":
            product = await db.get(Product, target_id)
            if product is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено.")
        elif kind == "comment":
            comment = await db.get(Review, target_id)
            if comment is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Коментар не знайдено.")

    duplicate_stmt = select(Report).where(
        Report.reporter_id == current_user.id,
        Report.status == "pending",
    )
    if payload.reported_user_id is not None:
        duplicate_stmt = duplicate_stmt.where(Report.reported_user_id == payload.reported_user_id)
    if payload.product_id is not None:
        duplicate_stmt = duplicate_stmt.where(Report.product_id == payload.product_id)
    if payload.comment_id is not None:
        duplicate_stmt = duplicate_stmt.where(Report.comment_id == payload.comment_id)

    existing_report = (await db.execute(duplicate_stmt)).scalar_one_or_none()
    if existing_report is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ви вже подали скаргу на цей об'єкт і вона ще в обробці.")

    report = Report(
        reporter_id=current_user.id,
        reported_user_id=payload.reported_user_id,
        product_id=payload.product_id,
        comment_id=payload.comment_id,
        reason=payload.reason,
        details=payload.details,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    background_tasks.add_task(notify_admins_about_new_report, report.id)

    return ReportResponse.model_validate(report)


@router.get("/admin/reports", response_model=list[ReportResponse])
async def list_reports_for_admin(
    status: str = Query(default="pending"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    allowed_statuses = {"pending", "resolved", "rejected"}
    normalized_status = status.lower()
    if normalized_status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недійсний статус.")

    stmt = (
        select(Report)
        .options(selectinload(Report.reporter), selectinload(Report.reported_user), selectinload(Report.product))
        .where(Report.status == normalized_status)
        .order_by(Report.created_at.desc())
    )
    reports = (await db.execute(stmt)).scalars().all()

    result = []
    for report in reports:
        reporter = report.reporter
        reported_user = report.reported_user
        product = report.product
        comment_preview = None
        if report.comment_id is not None:
            comment = await db.get(Review, report.comment_id)
            comment_preview = comment.comment if comment else None

        response = ReportResponse.model_validate(report)
        response.reporter_username = reporter.username if reporter else None
        response.reported_username = reported_user.username if reported_user else None
        response.product_title = product.title if product else None
        response.comment_preview = comment_preview
        result.append(response)

    return result
