from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_user, get_current_user_or_redirect, get_optional_current_user
from models import Comment, Complaint, Product, Report, User
from schemas import ComplaintCreate, ComplaintResponse, ReportCreate, ReportResponse, ReportStatusUpdate

router = APIRouter(tags=["complaints"])
templates = Jinja2Templates(directory="Templates")

REPORT_REASONS = {
    "шахрайство": "Шахрайство",
    "спам / спам-акаунт": "Спам / Спам-акаунт",
    "спам": "Спам / Спам-акаунт",
    "невідповідність товару": "Невідповідність товару",
    "нецензурна лексика": "Нецензурна лексика",
    "інше": "Інше",
    "fraud": "Шахрайство",
    "spam": "Спам / Спам-акаунт",
    "misrepresentation": "Невідповідність товару",
    "profanity": "Нецензурна лексика",
    "other": "Інше",
}


def normalize_reason(reason: str | None) -> str:
    if not reason:
        return "Інше"
    value = str(reason).strip()
    if not value:
        return "Інше"
    canonical = value.lower()
    return REPORT_REASONS.get(canonical, value)


def format_reason_label(reason: str | None) -> str:
    if not reason:
        return "Інше"
    return normalize_reason(reason)


async def _validate_report_target(db: AsyncSession, payload: ReportCreate) -> None:
    targets = [
        (payload.reported_user_id, "користувача"),
        (payload.product_id, "товар"),
        (payload.comment_id, "коментар"),
    ]
    active_targets = [target for target, _ in targets if target is not None]
    if not active_targets:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не вказано об'єкт скарги.")

    if payload.reported_user_id is not None:
        reported_user = await db.get(User, payload.reported_user_id)
        if reported_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача, на якого скаржаться, не знайдено.")

    if payload.product_id is not None:
        product = await db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено.")

    if payload.comment_id is not None:
        comment = await db.get(Comment, payload.comment_id)
        if comment is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Коментар не знайдено.")


@router.get("/api/v1/reports", response_model=list[ReportResponse])
async def list_reports(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Report).order_by(Report.created_at.desc())
    if not (current_user.is_admin or current_user.is_superuser):
        stmt = stmt.where(Report.reporter_id == current_user.id)
    reports = (await db.execute(stmt)).scalars().all()
    return [ReportResponse.model_validate(report) for report in reports]


@router.post("/api/v1/reports", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def create_report(
    payload: ReportCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _validate_report_target(db, payload)

    db_report = Report(
        reporter_id=current_user.id,
        reported_user_id=payload.reported_user_id,
        product_id=payload.product_id,
        comment_id=payload.comment_id,
        reason=normalize_reason(payload.reason),
        details=payload.details or payload.description,
        status=payload.status or "pending",
    )
    db.add(db_report)
    await db.commit()
    await db.refresh(db_report)
    return ReportResponse.model_validate(db_report)


@router.get("/api/v1/reports/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скаргу не знайдено.")
    if report.reporter_id != current_user.id and not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав.")
    return ReportResponse.model_validate(report)


@router.patch("/api/v1/reports/{report_id}/status", response_model=ReportResponse)
async def update_report_status(
    report_id: int,
    payload: ReportStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скаргу не знайдено.")

    report.status = payload.status
    await db.commit()
    await db.refresh(report)
    return ReportResponse.model_validate(report)


@router.get("/api/v1/complaints", response_model=list[ComplaintResponse])
async def list_complaints(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_reports(current_user=current_user, db=db)


@router.post("/api/v1/complaints", response_model=ComplaintResponse, status_code=status.HTTP_201_CREATED)
async def create_complaint(
    request: Request,
    payload: ComplaintCreate | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload is None:
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірний формат даних.")
            payload = ComplaintCreate(**body)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Невірні дані скарги.") from exc

    await _validate_report_target(db, payload)
    report = Report(
        reporter_id=current_user.id,
        reported_user_id=payload.reported_user_id,
        product_id=payload.product_id,
        comment_id=payload.comment_id,
        reason=normalize_reason(payload.reason),
        details=payload.details or payload.description,
        status="pending",
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    complaint_data = ComplaintResponse.model_validate(report)
    complaint_data.user_id = report.reporter_id
    complaint_data.username = current_user.username
    complaint_data.subject = format_reason_label(report.reason)
    complaint_data.title = complaint_data.subject
    complaint_data.text = report.details or ""
    complaint_data.comment = report.details or ""
    return complaint_data


@router.get("/api/v1/complaints/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint_detail(
    complaint_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, complaint_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скаргу не знайдено")
    if report.reporter_id != current_user.id and not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостатньо прав.")

    complaint_data = ComplaintResponse.model_validate(report)
    complaint_data.user_id = report.reporter_id
    complaint_data.username = current_user.username
    complaint_data.subject = format_reason_label(report.reason)
    complaint_data.title = complaint_data.subject
    complaint_data.text = report.details or ""
    complaint_data.comment = report.details or ""
    complaint_data.product_id = report.product_id
    complaint_data.target_type = "product" if report.product_id is not None else "user" if report.reported_user_id is not None else "comment"
    complaint_data.target_id = report.product_id or report.reported_user_id or report.comment_id
    return complaint_data


@router.patch("/api/v1/complaints/{complaint_id}/status")
async def update_complaint_status(
    complaint_id: int,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    report = await db.get(Report, complaint_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скаргу не знайдено")

    new_status = str((payload or {}).get("status") or "").strip().lower()
    allowed = {"pending", "resolved", "rejected", "opened", "in_progress"}
    if new_status not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Некоректний статус скарги")

    report.status = new_status if new_status in {"pending", "resolved", "rejected"} else "pending"
    await db.commit()
    await db.refresh(report)
    return {"message": "Статус скарги оновлено", "status": report.status}


@router.get("/complaints", response_class=HTMLResponse)
async def complaints_page(
    request: Request,
    result: User | RedirectResponse = Depends(get_current_user_or_redirect),
    db: AsyncSession = Depends(get_db),
):
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

    complaints = (await db.execute(select(Report).where(Report.reporter_id == current_user.id).order_by(Report.created_at.desc()))).scalars().all()
    view = []
    for item in complaints:
        product = await db.get(Product, item.product_id) if item.product_id is not None else None
        view.append({
            "id": item.id,
            "status": item.status,
            "reason": item.reason,
            "subject": format_reason_label(item.reason),
            "comment": item.details,
            "target_type": "product" if item.product_id is not None else "user" if item.reported_user_id is not None else "comment",
            "target_id": item.product_id or item.reported_user_id or item.comment_id,
            "product_title": product.title if product else None,
            "created_at": item.created_at,
            "reporter_id": item.reporter_id,
        })

    return templates.TemplateResponse(
        request,
        "complaints.html",
        {
            "request": request,
            "current_user": current_user,
            "complaints": view,
        },
    )
