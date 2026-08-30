from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_superuser, get_current_user
from models import Portfolio, Product, Report, Resume, Review, User
from schemas import UserPublic, UserRoleUpdate

BASE_DIR = Path(__file__).resolve().parent.parent
router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(BASE_DIR / "Templates"))


def is_protected_superadmin_user(user: User | None) -> bool:
    if user is None:
        return False
    return bool(user.is_superuser or getattr(user, "role", None) == "superadmin" or user.id == 1)


async def get_current_superadmin_or_redirect(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
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

    if current_user is None or not current_user.is_active:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not current_user.is_superuser:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return current_user


@router.get("/admin/manage-admins", response_class=HTMLResponse)
async def manage_admins_page(
    request: Request,
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

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
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

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

    original_username = target.username
    target.is_admin = True
    target.username = original_username
    await db.commit()
    return RedirectResponse(
        url=f"/admin/manage-admins?message=Користувача+{target.username}+призначено+адміном",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/demote/{user_id}")
async def demote_from_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

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

    original_username = target.username
    target.is_admin = False
    target.username = original_username
    await db.commit()
    return RedirectResponse(
        url=f"/admin/manage-admins?message=З+користувача+{target.username}+знято+права+адміна",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/admin/users/delete/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

    target = await db.get(User, user_id)
    if target is None:
        return RedirectResponse(
            url="/admin/manage-admins?error=Користувача+не+знайдено",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    if is_protected_superadmin_user(target):
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


@router.patch("/api/v1/admin/reports/{report_id}/status")
async def update_report_status(
    report_id: int,
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    report = await db.get(Report, report_id)
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Скаргу не знайдено")

    body = payload or {}
    new_status = str(body.get("status", "")).strip().lower()
    action = str(body.get("action", "none")).strip().lower()
    allowed_actions = {"ban_user", "delete_product", "delete_comment", "none"}

    if new_status not in {"resolved", "rejected"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недійсний статус скарги")
    if action not in allowed_actions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недійсний тип дії")

    report.status = new_status

    if new_status == "resolved":
        if action == "ban_user":
            target_user = None
            if report.reported_user_id is not None:
                target_user = await db.get(User, report.reported_user_id)
            elif report.product_id is not None:
                product = await db.get(Product, report.product_id)
                if product is not None:
                    target_user = await db.get(User, product.user_id)
            elif report.comment_id is not None:
                comment = await db.get(Review, report.comment_id)
                if comment is not None:
                    target_user = await db.get(User, comment.user_id)

            if target_user is not None and target_user.id != current_user.id:
                target_user.is_active = False
                target_user.is_banned = True
                target_user.banned_until = None

        if action == "delete_product" and report.product_id is not None:
            product = await db.get(Product, report.product_id)
            if product is not None:
                await db.delete(product)

        if action == "delete_comment" and report.comment_id is not None:
            comment = await db.get(Review, report.comment_id)
            if comment is not None:
                await db.delete(comment)

    await db.commit()
    return {
        "status": "updated",
        "report_id": report.id,
        "report_status": report.status,
        "action": action,
    }


@router.get("/api/v1/admin/reports")
async def get_reports_for_admin(
    status: str = "pending",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    normalized_status = status.lower()
    allowed_statuses = {"pending", "resolved", "rejected"}
    if normalized_status not in allowed_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недійсний статус")

    stmt = select(Report).where(Report.status == normalized_status).order_by(Report.created_at.desc())
    reports = (await db.execute(stmt)).scalars().all()

    result = []
    for report in reports:
        reporter = await db.get(User, report.reporter_id)
        reported_user = await db.get(User, report.reported_user_id) if report.reported_user_id is not None else None
        product = await db.get(Product, report.product_id) if report.product_id is not None else None
        comment = await db.get(Review, report.comment_id) if report.comment_id is not None else None

        payload = {
            "id": report.id,
            "reporter_id": report.reporter_id,
            "reporter_username": reporter.username if reporter else None,
            "reported_user_id": report.reported_user_id,
            "reported_username": reported_user.username if reported_user else None,
            "product_id": report.product_id,
            "product_title": product.title if product else None,
            "product_url": f"/products/{product.id}" if product else None,
            "comment_id": report.comment_id,
            "comment_preview": (comment.comment[:120] if comment and comment.comment else None),
            "comment_url": None,
            "reason": report.reason,
            "details": report.details,
            "status": report.status,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "target_type": "user" if report.reported_user_id is not None else "product" if report.product_id is not None else "comment" if report.comment_id is not None else "unknown",
        }

        if comment is not None:
            payload["comment_url"] = f"/products/{comment.product_id}#review-{comment.id}"

        result.append(payload)

    return result


@router.get("/api/v1/admin/banned-users")
async def get_banned_users(
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

    users = (await db.execute(
        select(User).where(User.is_banned.is_(True)).order_by(User.id.desc())
    )).scalars().all()
    result = []
    for user in users:
        result.append({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
            "is_superuser": user.is_superuser,
            "is_banned": user.is_banned,
            "banned_until": user.banned_until,
            "banned_until_text": user.banned_until.isoformat() if user.banned_until else "Постійно",
        })
    return result


@router.post("/api/v1/admin/users/{user_id}/unban")
async def unban_user_by_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if is_protected_superadmin_user(target):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заборонено банити головного адміністратора (Superadmin)")
    if target.is_admin and not _current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only superadmin can unban admins")

    target.is_banned = False
    target.banned_until = None
    target.is_active = True
    await db.commit()
    await db.refresh(target)
    return {"status": "unbanned", "user_id": target.id}


@router.get("/api/v1/admin/portfolio")
async def admin_get_portfolios(
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

    portfolios = (await db.execute(select(Portfolio).options(joinedload(Portfolio.user)).order_by(Portfolio.created_at.desc()))).scalars().unique().all()
    result = []
    for item in portfolios:
        user = item.user
        result.append({
            "id": item.id,
            "user_id": item.user_id,
            "username": user.username if user else None,
            "display_name": user.display_name if user else None,
            "email": user.email if user else None,
            "title": item.title,
            "specialty": item.specialty,
            "experience_years": item.experience_years,
            "skills": item.skills,
            "summary": item.summary,
            "bio": item.bio,
            "public_contacts": item.public_contacts,
            "phone": item.phone,
            "telegram": item.telegram,
            "public_email": item.public_email,
            "status": item.status,
            "created_at": item.created_at,
        })
    return result


@router.delete("/api/v1/admin/portfolio/{portfolio_id}")
async def delete_portfolio_by_admin(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

    portfolio = await db.get(Portfolio, portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Portfolio not found")

    await db.delete(portfolio)
    await db.commit()
    return {"status": "deleted"}


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
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

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
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

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
    _current_user = Depends(get_current_superadmin_or_redirect),
):
    if isinstance(_current_user, RedirectResponse):
        return _current_user

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
