from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import Complaint, Product, User
from schemas import ComplaintCreate, ComplaintResponse

router = APIRouter(tags=["complaints"])
templates = Jinja2Templates(directory="Templates")


@router.get("/complaints", response_class=HTMLResponse)
async def complaints_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = None
    token_value = request.cookies.get("access_token")
    if token_value:
        try:
            payload = decode_access_token(token_value.replace("Bearer ", "").strip())
            user_id = payload.get("sub")
            if user_id is not None:
                current_user = await db.get(User, int(user_id))
        except Exception:
            current_user = None

    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    complaints = (
        await db.execute(
            select(Complaint)
            .where(Complaint.reporter_id == current_user.id)
            .order_by(Complaint.created_at.desc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "complaints.html",
        {"request": request, "current_user": current_user, "complaints": complaints},
    )


@router.get("/api/v1/complaints", response_model=list[ComplaintResponse])
async def list_complaints(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    complaints = (
        await db.execute(
            select(Complaint)
            .where(Complaint.reporter_id == current_user.id)
            .order_by(Complaint.created_at.desc())
        )
    ).scalars().all()
    return [ComplaintResponse.model_validate(item) for item in complaints]


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
