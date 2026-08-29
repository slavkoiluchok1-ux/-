from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from database import get_db
from dependencies import get_current_admin_user, get_current_superuser, get_current_superuser_or_redirect
from models import Comment, Product, Report, Resume, User

BASE_DIR = Path(__file__).resolve().parent.parent
router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "Templates"))


def build_report_admin_link(report_id: int) -> str:
    return f"/admin?tab=complaints&report_id={report_id}"


@router.patch("/api/v1/admin/reports/{report_id}/status")
async def admin_update_report_status(
    report_id: int,
    status_value: str = Form(...),
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Скаргу не знайдено")

    normalized = (status_value or "").strip().lower()
    if normalized not in {"pending", "resolved", "rejected"}:
        raise HTTPException(status_code=400, detail="Некоректний статус скарги")

    report.status = normalized
    await db.commit()
    await db.refresh(report)
    return {"id": report.id, "status": report.status, "message": "Статус скарги оновлено"}


@router.post("/api/v1/admin/reports/{report_id}/resolve")
async def admin_resolve_report(
    report_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Скаргу не знайдено")

    if report.reported_user_id is not None:
        target_user = await db.get(User, report.reported_user_id)
        if target_user is not None:
            target_user.is_banned = True
            target_user.is_active = False
    elif report.product_id is not None:
        product = await db.get(Product, report.product_id)
        if product is not None:
            await db.delete(product)
    elif report.comment_id is not None:
        comment = await db.get(Comment, report.comment_id)
        if comment is not None:
            await db.delete(comment)

    report.status = "resolved"
    await db.commit()
    return {"id": report.id, "status": report.status, "message": "Об'єкт заблоковано / скаргу прийнято"}


@router.post("/api/v1/admin/reports/{report_id}/reject")
async def admin_reject_report(
    report_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Скаргу не знайдено")

    report.status = "rejected"
    await db.commit()
    await db.refresh(report)
    return {"id": report.id, "status": report.status, "message": "Скаргу відхилено"}


@router.get("/api/v1/admin/reports/{report_id}/target")
async def admin_open_report_target(
    report_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Скаргу не знайдено")

    if report.product_id is not None:
        product = await db.get(Product, report.product_id)
        if product is not None:
            return {"type": "product", "url": f"/products/{product.id}"}
        return {"type": "product", "url": None}

    if report.reported_user_id is not None:
        target_user = await db.get(User, report.reported_user_id)
        if target_user is not None:
            return {"type": "user", "url": f"/profile?user_id={target_user.id}"}
        return {"type": "user", "url": None}

    if report.comment_id is not None:
        comment = await db.get(Comment, report.comment_id)
        if comment is not None:
            product = await db.get(Product, comment.product_id)
            if product is not None:
                return {"type": "comment", "url": f"/products/{product.id}#comment-{comment.id}"}
        return {"type": "comment", "url": None}

    return {"type": "unknown", "url": None}


@router.get("/admin/manage-admins", response_class=HTMLResponse)
async def manage_admins_page(
    request: Request,
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    stmt = select(User).order_by(User.is_superuser.desc(), User.is_admin.desc(), User.id.asc())

    if q and q.strip():
        term = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                User.username.ilike(term),
                User.email.ilike(term),
                (User.display_name != None) & (User.display_name.ilike(term)),
            )
        )

    raw_users = (await db.execute(stmt)).scalars().all()
    users = []
    for u in raw_users:
        users.append(u)

    if role and role.strip():
        role_value = role.strip().lower()
        if role_value == "superadmin":
            users = [u for u in users if u.is_superuser]
        elif role_value == "admin":
            users = [u for u in users if not u.is_superuser and u.is_admin]
        elif role_value == "user":
            users = [u for u in users if not u.is_superuser and not u.is_admin]

    view_users = []
    for u in users:
        if u.is_superuser:
            role_label = "Superadmin"
        elif u.is_admin:
            role_label = "Admin"
        else:
            role_label = "User"
        view_users.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "display_name": u.display_name,
            "role_label": role_label,
            "is_superuser": u.is_superuser,
            "is_admin": u.is_admin,
            "is_active": u.is_active,
            "created_at": u.created_at,
        })

    message = request.query_params.get("message")
    error = request.query_params.get("error")

    return templates.TemplateResponse(
        request,
        "admin/manage_admins.html",
        {
            "request": request,
            "current_user": _current_user,
            "users": view_users,
            "q": q or "",
            "role": role or "",
            "message": message,
            "error": error,
        },
    )


@router.post("/admin/promote/{user_id}")
async def promote_to_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    target = await db.get(User, user_id)
    if target is None:
        return RedirectResponse(
            url="/admin/manage-admins?error=Користувача+не+знайдено",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if target.is_superuser:
        return RedirectResponse(
            url="/admin/manage-admins?error=Неможливо+змінити+роль+супер+адміна",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if target.is_admin:
        return RedirectResponse(
            url="/admin/manage-admins?message=Користувач+вже+є+адміном",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    target.is_admin = True
    await db.commit()
    return RedirectResponse(
        url=f"/admin/manage-admins?message=Користувача+{target.username}+призначено+адміном",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/demote/{user_id}")
async def demote_from_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    target = await db.get(User, user_id)
    if target is None:
        return RedirectResponse(
            url="/admin/manage-admins?error=Користувача+не+знайдено",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if target.is_superuser:
        return RedirectResponse(
            url="/admin/manage-admins?error=Неможливо+знищити+роль+супер+адміна",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if not target.is_admin:
        return RedirectResponse(
            url="/admin/manage-admins?message=Користувач+не+є+адміном",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    target.is_admin = False
    await db.commit()
    return RedirectResponse(
        url=f"/admin/manage-admins?message=З+користувача+{target.username}+знято+права+адміна",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/users/delete/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    target = await db.get(User, user_id)
    if target is None:
        return RedirectResponse(
            url="/admin/manage-admins?error=Користувача+не+знайдено",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if target.is_superuser:
        return RedirectResponse(
            url="/admin/manage-admins?error=Неможливо+видалити+супер+адміна",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if _current_user.id == target.id:
        return RedirectResponse(
            url="/admin/manage-admins?error=Неможливо+видалити+власний+акаунт",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await db.delete(target)
    await db.commit()
    return RedirectResponse(
        url="/admin/manage-admins?message=Користувач+видалений",
        status_code=status.HTTP_303_SEE_OTHER,
    )


ALLOWED_RESUME_STATUSES = {"pending", "reviewing", "accepted", "rejected"}
RESUME_STATUS_LABELS = {
    "pending": "На розгляді",
    "reviewing": "Перевіряється",
    "accepted": "Прийнято",
    "rejected": "Відхилено",
}


def _resume_status_label(value: str) -> str:
    return RESUME_STATUS_LABELS.get(value or "pending", value or "pending")


@router.get("/admin/resumes", response_class=HTMLResponse)
async def manage_resumes_page(
    request: Request,
    q: Optional[str] = Query(default=None),
    filter_status: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    stmt = select(Resume).options(joinedload(Resume.user)).order_by(Resume.updated_at.desc(), Resume.created_at.desc())

    if filter_status and filter_status.strip() in ALLOWED_RESUME_STATUSES:
        stmt = stmt.where(Resume.status == filter_status.strip())

    resumes = (await db.execute(stmt)).scalars().unique().all()

    if q and q.strip():
        term = q.strip().lower()

        def _match(resume: Resume) -> bool:
            haystacks = []
            if resume.title:
                haystacks.append(resume.title.lower())
            if resume.specialty:
                haystacks.append(resume.specialty.lower())
            if resume.summary:
                haystacks.append(resume.summary.lower())
            if resume.bio:
                haystacks.append(resume.bio.lower())
            if resume.skills:
                haystacks.append(resume.skills.lower())
            if resume.experience:
                haystacks.append(resume.experience.lower())
            if resume.display_name:
                haystacks.append(resume.display_name.lower())
            if resume.public_email:
                haystacks.append(resume.public_email.lower())
            if resume.phone:
                haystacks.append(resume.phone.lower())
            user = resume.user
            if user:
                if user.username:
                    haystacks.append(user.username.lower())
                if user.email:
                    haystacks.append(user.email.lower())
                if user.display_name:
                    haystacks.append(user.display_name.lower())
            return any(term in h for h in haystacks)

        resumes = [r for r in resumes if _match(r)]

    view_resumes = []
    for r in resumes:
        user = r.user
        view_resumes.append({
            "id": r.id,
            "user_id": r.user_id,
            "username": user.username if user else None,
            "email": user.email if user else None,
            "user_display_name": user.display_name if user else None,
            "title": r.title,
            "specialty": r.specialty,
            "experience_years": r.experience_years,
            "experience": r.experience,
            "skills": r.skills,
            "bio": r.bio,
            "summary": r.summary,
            "public_contacts": r.public_contacts,
            "cv_file_path": r.cv_file_path,
            "display_name": r.display_name,
            "phone": r.phone,
            "viber": r.viber,
            "telegram": r.telegram,
            "instagram": r.instagram,
            "whatsapp": r.whatsapp,
            "public_email": r.public_email,
            "status": r.status or "pending",
            "status_label": _resume_status_label(r.status),
            "created_at": r.created_at,
            "updated_at": r.updated_at,
        })

    message = request.query_params.get("message")
    error = request.query_params.get("error")

    return templates.TemplateResponse(
        request,
        "admin/resumes.html",
        {
            "request": request,
            "current_user": _current_user,
            "resumes": view_resumes,
            "statuses": sorted(ALLOWED_RESUME_STATUSES),
            "status_labels": RESUME_STATUS_LABELS,
            "q": q or "",
            "filter_status": filter_status or "",
            "message": message,
            "error": error,
        },
    )


@router.post("/admin/resumes/{resume_id}/status")
async def update_resume_status(
    resume_id: int,
    new_status: str = Form(...),
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    resume = await db.get(Resume, resume_id)
    if resume is None:
        return RedirectResponse(
            url="/admin/resumes?error=Резюме+не+знайдено",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    normalized = (new_status or "").strip().lower()
    if normalized not in ALLOWED_RESUME_STATUSES:
        return RedirectResponse(
            url="/admin/resumes?error=Некоректний+статус",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    resume.status = normalized
    await db.commit()
    label = _resume_status_label(normalized)
    return RedirectResponse(
        url=f"/admin/resumes?message=Статус+резюме+#{resume.id}+оновлено+на+{label}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/resumes/{resume_id}/delete")
async def delete_resume(
    resume_id: int,
    db: AsyncSession = Depends(get_db),
    result = Depends(get_current_superuser_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    _current_user = result

    resume = await db.get(Resume, resume_id)
    if resume is None:
        return RedirectResponse(
            url="/admin/resumes?error=Резюме+не+знайдено",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    await db.delete(resume)
    await db.commit()
    return RedirectResponse(
        url="/admin/resumes?message=Резюме+видалено",
        status_code=status.HTTP_303_SEE_OTHER,
    )
