from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import Complaint, Product, Review, ReviewMedia, User
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
        comment = await db.get(Review, item.target_id) if item.target_type == "comment" else None
        complaint_data = ComplaintResponse.model_validate(item)
        complaint_data.user_id = item.reporter_id
        complaint_data.username = reporter.username if reporter else None
        complaint_data.user_email = reporter.email if reporter else None
        complaint_data.product_id = item.target_id if item.target_type == "product" else None
        complaint_data.target_user_id = item.target_user_id or (comment.user_id if comment else None)
        complaint_data.subject = format_reason_label(item.reason)
        complaint_data.title = complaint_data.subject
        complaint_data.text = item.comment or ""
        complaint_data.target_text = comment.comment if comment else None
        if item.target_type == "product" and product is not None:
            complaint_data.object_label = f'Товар "{product.title}" (ID: {product.id})'
        elif item.target_type == "comment" and comment is not None:
            author = await db.get(User, comment.user_id)
            complaint_data.object_label = f'Коментар "{(comment.comment or "").strip()[:120]}" (ID: {comment.id})'
            complaint_data.username = author.username if author else complaint_data.username
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

    target_type = (payload.target_type or "product").lower()
    target_id = payload.target_id if payload.target_id is not None else payload.product_id
    if target_type == "comment":
        if target_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Відсутній ID коментаря.")
        review = await db.get(Review, target_id)
        if review is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Коментар не знайдено.")
        target_user_id = payload.target_user_id or review.user_id
        complaint = Complaint(
            reporter_id=current_user.id,
            target_type="comment",
            target_id=target_id,
            target_user_id=target_user_id,
            reason=payload.reason,
            comment=payload.description or review.comment,
            status="opened",
        )
    elif target_type == "user":
        if target_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Відсутній ID користувача.")
        target_user = await db.get(User, target_id)
        if target_user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено.")
        complaint = Complaint(
            reporter_id=current_user.id,
            target_type="user",
            target_id=target_id,
            target_user_id=target_id,
            reason=payload.reason,
            comment=payload.description,
            status="opened",
        )
    else:
        product_id = payload.product_id if payload.product_id is not None else target_id
        if product_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Відсутній ID товару.")
        product = await db.get(Product, product_id)
        if product is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено.")
        complaint = Complaint(
            reporter_id=current_user.id,
            target_type="product",
            target_id=product_id,
            target_user_id=payload.target_user_id or product.user_id,
            reason=payload.reason,
            comment=payload.description,
            status="opened",
        )

    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)
    return ComplaintResponse.model_validate(complaint)


@router.delete("/api/v1/admin/comments/{comment_id}")
async def delete_comment_by_admin(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    review = await db.get(Review, comment_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Коментар не знайдено")

    await db.execute(delete(ReviewMedia).where(ReviewMedia.review_id == comment_id))
    await db.delete(review)
    await db.commit()
    return {"message": "Коментар видалено"}


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
