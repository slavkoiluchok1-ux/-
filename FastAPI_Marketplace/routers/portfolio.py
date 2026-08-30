from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import decode_access_token
from database import get_db
from models import Portfolio, User

router = APIRouter(tags=["portfolio"])
templates = Jinja2Templates(directory="Templates")
PORTFOLIO_UPLOAD_DIR = Path(__file__).resolve().parents[1] / "static" / "uploads" / "cv"
PORTFOLIO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_PORTFOLIO_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".webp"}


async def _get_user_from_request(request: Request, db: AsyncSession) -> User | None:
    token_value = request.cookies.get("access_token")
    if not token_value:
        return None
    try:
        payload = decode_access_token(token_value.replace("Bearer ", "").strip())
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return await db.get(User, int(user_id))
    except Exception:
        return None


async def _get_portfolio_for_user(db: AsyncSession, user_id: int) -> Portfolio | None:
    return await db.scalar(select(Portfolio).where(Portfolio.user_id == user_id))


async def _save_cv_file(file: UploadFile | None) -> str | None:
    if file is None or file.filename is None or not file.filename.strip():
        return None

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_PORTFOLIO_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Дозволені типи файлів: PDF, DOC, DOCX, PNG, JPG, JPEG, WEBP.",
        )

    content = await file.read()
    safe_name = Path(file.filename).name.replace(" ", "_")
    unique_name = f"{uuid.uuid4()}_{safe_name}"
    save_path = PORTFOLIO_UPLOAD_DIR / unique_name
    save_path.write_bytes(content)
    return f"/static/uploads/cv/{unique_name}"


@router.get("/portfolio", response_class=HTMLResponse)
async def portfolio_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await _get_user_from_request(request, db)
    current_portfolio = None
    if current_user is not None:
        current_portfolio = await _get_portfolio_for_user(db, current_user.id)

    stmt = select(Portfolio).where(Portfolio.user_id != (current_user.id if current_user else -1))
    portfolios = (await db.execute(stmt)).scalars().all()
    other_portfolios = []
    for item in portfolios:
        user = await db.get(User, item.user_id)
        if user is not None and (user.is_active or user.id == (current_user.id if current_user else -1)):
            other_portfolios.append({"portfolio": item, "user": user})

    return templates.TemplateResponse(
        request,
        "portfolio.html",
        {
            "request": request,
            "current_user": current_user,
            "portfolio": current_portfolio,
            "portfolios": other_portfolios,
            "has_current_portfolio": current_portfolio is not None,
            "view_user": current_user,
        },
    )


@router.get("/portfolio/{user_id}", response_class=HTMLResponse)
async def public_portfolio_page(request: Request, user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Користувача не знайдено")

    current_user = await _get_user_from_request(request, db)
    portfolio = await _get_portfolio_for_user(db, user.id)
    if portfolio is None:
        return RedirectResponse(url="/portfolio", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "portfolio.html",
        {
            "request": request,
            "current_user": current_user,
            "portfolio": portfolio,
            "portfolios": [],
            "has_current_portfolio": bool(current_user and await _get_portfolio_for_user(db, current_user.id)),
            "view_user": user,
            "is_owner": bool(current_user and current_user.id == user.id),
        },
    )


@router.get("/api/v1/portfolio/{user_id}")
async def get_public_portfolio(user_id: int, db: AsyncSession = Depends(get_db)):
    portfolio = await _get_portfolio_for_user(db, user_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Портфоліо не знайдено")
    return {
        "id": portfolio.id,
        "user_id": portfolio.user_id,
        "title": portfolio.title,
        "specialty": portfolio.specialty,
        "experience_years": portfolio.experience_years,
        "experience": portfolio.experience,
        "skills": portfolio.skills,
        "bio": portfolio.bio,
        "summary": portfolio.summary,
        "public_contacts": portfolio.public_contacts,
        "cv_file_path": portfolio.cv_file_path,
    }


@router.post("/portfolio")
async def submit_portfolio_page(
    request: Request,
    title: str = Form(default=""),
    specialty: str = Form(default=""),
    experience_years: str = Form(default=""),
    experience: str = Form(default=""),
    skills: str = Form(default=""),
    bio: str = Form(default=""),
    summary: str = Form(default=""),
    public_contacts: str = Form(default=""),
    phone: str = Form(default=""),
    telegram: str = Form(default=""),
    public_email: str = Form(default=""),
    cv_file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
):
    current_user = await _get_user_from_request(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    portfolio = await _get_portfolio_for_user(db, current_user.id)
    cv_path = await _save_cv_file(cv_file)

    if portfolio is None:
        portfolio = Portfolio(user_id=current_user.id)
        db.add(portfolio)

    portfolio.title = (title or specialty or "").strip() or portfolio.title
    portfolio.specialty = (specialty or title or "").strip() or portfolio.specialty
    portfolio.experience_years = experience_years.strip() or portfolio.experience_years
    portfolio.experience = experience.strip() or portfolio.experience
    portfolio.skills = skills.strip() or portfolio.skills
    portfolio.bio = bio.strip() or portfolio.bio
    portfolio.summary = summary.strip() or bio.strip() or portfolio.summary
    portfolio.public_contacts = public_contacts.strip() or portfolio.public_contacts
    portfolio.phone = phone.strip() or portfolio.phone
    portfolio.telegram = telegram.strip() or portfolio.telegram
    portfolio.public_email = public_email.strip() or portfolio.public_email
    if cv_path:
        portfolio.cv_file_path = cv_path

    await db.commit()
    await db.refresh(portfolio)
    return RedirectResponse(url=f"/portfolio/{current_user.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/v1/portfolio")
async def upsert_portfolio(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_user = await _get_user_from_request(request, db)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required")

    form = await request.form()
    title = str(form.get("title") or form.get("specialty") or "").strip()
    specialty = str(form.get("specialty") or form.get("title") or "").strip()
    experience_years = str(form.get("experience_years") or "").strip()
    experience = str(form.get("experience") or "").strip()
    skills = str(form.get("skills") or "").strip()
    bio = str(form.get("bio") or "").strip()
    summary = str(form.get("summary") or bio or "").strip()
    public_contacts = str(form.get("public_contacts") or "").strip()
    phone = str(form.get("phone") or "").strip()
    telegram = str(form.get("telegram") or "").strip()
    public_email = str(form.get("public_email") or "").strip()
    cv_file = form.get("cv_file")

    portfolio = await _get_portfolio_for_user(db, current_user.id)
    if portfolio is None:
        portfolio = Portfolio(user_id=current_user.id)
        db.add(portfolio)

    portfolio.title = title or portfolio.title
    portfolio.specialty = specialty or portfolio.specialty
    portfolio.experience_years = experience_years or portfolio.experience_years
    portfolio.experience = experience or portfolio.experience
    portfolio.skills = skills or portfolio.skills
    portfolio.bio = bio or portfolio.bio
    portfolio.summary = summary or portfolio.summary
    portfolio.public_contacts = public_contacts or portfolio.public_contacts
    portfolio.phone = phone or portfolio.phone
    portfolio.telegram = telegram or portfolio.telegram
    portfolio.public_email = public_email or portfolio.public_email

    cv_path = await _save_cv_file(cv_file) if cv_file is not None and hasattr(cv_file, "read") else None
    if cv_path:
        portfolio.cv_file_path = cv_path

    await db.commit()
    await db.refresh(portfolio)
    return {"status": "ok", "portfolio_id": portfolio.id, "message": "Портфоліо успішно збережено"}
