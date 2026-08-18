from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import Complaint, Product, User
from schemas import ComplaintCreate, ComplaintResponse

router = APIRouter(tags=["complaints"])
templates = Jinja2Templates(directory="Templates")

REASON_LABELS = {
    "profanity": "Нецензурна лексика",
    "threats": "Погрози",
    "sexual": "Контент сексуального характеру",
    "fraud": "Шахрайство",
    "spam": "Спам / Реклама",
    "other": "Інше",
}


def format_reason_label(reason: str | None) -> str:
    if not reason:
        return "Інше"
    return REASON_LABELS.get(reason, reason)


@router.get("/api/v1/complaints", response_model=list[ComplaintResponse])
async def list_complaints(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    stmt = select(Complaint).options(selectinload(Complaint.reporter))
    if current_user.is_admin or current_user.is_superuser:
        stmt = stmt.order_by(Complaint.created_at.desc())
    else:
        stmt = stmt.where(Complaint.reporter_id == current_user.id).order_by(Complaint.created_at.desc())
    complaints = (await db.execute(stmt)).scalars().all()
    result = []
    for item in complaints:
        reporter = await db.get(User, item.reporter_id)
        product = await db.get(Product, item.target_id) if item.target_type == "product" else None
        complaint_data = ComplaintResponse.model_validate(item)
        complaint_data.user_id = item.reporter_id
        complaint_data.username = reporter.username if reporter else None
        complaint_data.user_email = reporter.email if reporter else None
        complaint_data.product_id = item.target_id if item.target_type == "product" else None
        complaint_data.subject = format_reason_label(item.reason)
        complaint_data.title = complaint_data.subject
        complaint_data.text = item.comment or ""
        if item.target_type == "product" and product is not None:
            complaint_data.object_label = f'Товар "{product.title}" (ID: {product.id})'
        elif reporter is not None:
            complaint_data.object_label = f'Користувач "{reporter.username}" (ID: {reporter.id})'
        result.append(complaint_data)
    return result


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

    product = await db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено.")

    complaint = Complaint(
        reporter_id=current_user.id,
        target_type="product",
        target_id=payload.product_id,
        reason=payload.reason,
        comment=payload.description,
        status="opened",
    )
    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)


@router.get("/api/v1/complaints/{complaint_id}", response_model=ComplaintResponse)
async def get_complaint_detail(
    complaint_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    complaint = await db.get(Complaint, complaint_id)
    if not complaint or complaint.reporter_id != current_user.id:
        raise HTTPException(status_code=404, detail="Скаргу не знайдено")
    return ComplaintResponse.model_validate(complaint)
