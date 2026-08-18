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
from dependencies import get_current_user
from models import Resume, User

router = APIRouter(tags=["resume"])
templates = Jinja2Templates(directory="Templates")
CV_UPLOAD_DIR = Path(__file__).resolve().parents[1] / "static" / "uploads" / "cv"
CV_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_CV_EXTENSIONS = {".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".webp"}


async def _get_resume_for_user(db: AsyncSession, user_id: int) -> Resume | None:
    return await db.scalar(select(Resume).where(Resume.user_id == user_id))


async def _save_cv_file(file: UploadFile | None) -> str | None:
    if file is None or file.filename is None or not file.filename.strip():
        return None

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_CV_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Дозволені типи файлів: PDF, DOC, DOCX, PNG, JPG, JPEG, WEBP.",
        )

    content = await file.read()
    safe_name = Path(file.filename).name.replace(" ", "_")
    unique_name = f"{uuid.uuid4()}_{safe_name}"
    save_path = CV_UPLOAD_DIR / unique_name
    save_path.write_bytes(content)
    return f"/static/uploads/cv/{unique_name}"


@router.get("/resume", response_class=HTMLResponse)
async def resume_page(request: Request, db: AsyncSession = Depends(get_db)):
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

    resume = await _get_resume_for_user(db, current_user.id)
    return templates.TemplateResponse(
        request,
        "resume.html",
        {
            "request": request,
            "current_user": current_user,
            "resume": resume,
            "profile_user": current_user,
            "is_owner": True,
        },
    )


@router.get("/resume/{user_id}", response_class=HTMLResponse)
async def public_resume_page(request: Request, user_id: int, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Кандидата не знайдено")

    resume = await _get_resume_for_user(db, user.id)
    current_user = None
    token_value = request.cookies.get("access_token")
    if token_value:
        try:
            payload = decode_access_token(token_value.replace("Bearer ", "").strip())
            current_user_id = payload.get("sub")
            if current_user_id is not None:
                current_user = await db.get(User, int(current_user_id))
        except Exception:
            current_user = None

    return templates.TemplateResponse(
        request,
        "resume.html",
        {
            "request": request,
            "current_user": current_user,
            "resume": resume,
            "profile_user": user,
            "is_owner": bool(current_user and current_user.id == user.id),
        },
    )


@router.get("/api/v1/resume/{user_id}")
async def get_public_resume(user_id: int, db: AsyncSession = Depends(get_db)):
    resume = await _get_resume_for_user(db, user_id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Резюме не знайдено")
    return {
        "id": resume.id,
        "user_id": resume.user_id,
        "title": resume.title,
        "specialty": resume.specialty,
        "experience_years": resume.experience_years,
        "experience": resume.experience,
        "skills": resume.skills,
        "bio": resume.bio,
        "summary": resume.summary,
        "public_contacts": resume.public_contacts,
        "cv_file_path": resume.cv_file_path,
    }


@router.post("/resume")
async def submit_resume_page(
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
    current_user: User = Depends(get_current_user),
):
    resume = await _get_resume_for_user(db, current_user.id)
    cv_path = await _save_cv_file(cv_file)

    if resume is None:
        resume = Resume(user_id=current_user.id)
        db.add(resume)

    resume.title = (title or specialty or "").strip() or resume.title
    resume.specialty = (specialty or title or "").strip() or resume.specialty
    resume.experience_years = experience_years.strip() or resume.experience_years
    resume.experience = experience.strip() or resume.experience
    resume.skills = skills.strip() or resume.skills
    resume.bio = bio.strip() or resume.bio
    resume.summary = summary.strip() or bio.strip() or resume.summary
    resume.public_contacts = public_contacts.strip() or resume.public_contacts
    resume.phone = phone.strip() or resume.phone
    resume.telegram = telegram.strip() or resume.telegram
    resume.public_email = public_email.strip() or resume.public_email
    if cv_path:
        resume.cv_file_path = cv_path

    await db.commit()
    await db.refresh(resume)
    return RedirectResponse(url="/resume", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/v1/resume")
async def upsert_resume(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    title = str(payload.get("title") or payload.get("specialty") or "").strip()
    specialty = str(payload.get("specialty") or payload.get("title") or "").strip()
    experience_years = str(payload.get("experience_years") or "").strip()
    experience = str(payload.get("experience") or "").strip()
    skills = str(payload.get("skills") or "").strip()
    bio = str(payload.get("bio") or "").strip()
    summary = str(payload.get("summary") or bio or "").strip()
    public_contacts = str(payload.get("public_contacts") or "").strip()
    cv_file = None

    if "cv_file" in payload:
        file_obj = payload.get("cv_file")
        if hasattr(file_obj, "read"):
            cv_file = file_obj

    if "application/json" not in content_type and "cv_file" in request._form:
        cv_file = request._form.get("cv_file")

    resume = await _get_resume_for_user(db, current_user.id)
    if resume is None:
        resume = Resume(user_id=current_user.id)
        db.add(resume)

    resume.title = title or resume.title
    resume.specialty = specialty or resume.specialty
    resume.experience_years = experience_years or resume.experience_years
    resume.experience = experience or resume.experience
    resume.skills = skills or resume.skills
    resume.bio = bio or resume.bio
    resume.summary = summary or resume.summary
    resume.public_contacts = public_contacts or resume.public_contacts

    cv_path = await _save_cv_file(cv_file) if cv_file is not None else None
    if cv_path:
        resume.cv_file_path = cv_path

    await db.commit()
    await db.refresh(resume)
    return {"status": "ok", "resume_id": resume.id, "message": "Резюме успішно подано"}
