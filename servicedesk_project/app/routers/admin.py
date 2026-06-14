from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.bot.tg_bot import send_msg
from app.database import get_session
from app.models import Problem, User, AdminResponse, ServiceRecord
from app.security import get_current_user, get_current_user_optional

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="templates")

@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: tuple = Depends(get_current_user), db_user = Depends(get_current_user_optional), session: AsyncSession = Depends(get_session)):
    _, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403, detail="Доступ заборонено")
        
    res = await session.execute(select(Problem).options(selectinload(Problem.user)))
    problems = res.scalars().all()
    return templates.TemplateResponse(request, "dashboard_admin.html", {"problems": problems, "user": db_user})

@router.get("/workers", response_class=HTMLResponse)
async def manage_workers(request: Request, current_user: tuple = Depends(get_current_user), db_user = Depends(get_current_user_optional), session: AsyncSession = Depends(get_session)):
    _, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403, detail="Доступ заборонено")
        
    res = await session.execute(select(User))
    all_users = res.scalars().all()
    return templates.TemplateResponse(request, "admin_workers.html", {"all_users": all_users, "user": db_user})

@router.post("/user/{user_id}/change-role")
async def change_user_role(user_id: int, new_role: str = Form(), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    _, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403)
        
    res = await session.execute(select(User).filter(User.id == user_id))
    target_user = res.scalars().first()
    if target_user:
        target_user.role = new_role
        await session.commit()
    return RedirectResponse(url="/admin/workers", status_code=303)

@router.post("/problem/{problem_id}/assign")
async def assign_worker(problem_id: int, worker_id: int = Form(), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    _, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403)
        
    res = await session.execute(select(Problem).filter(Problem.id == problem_id))
    problem = res.scalars().first()
    if problem:
        problem.worker_id = worker_id
        problem.status = "Призначено майстра"
        await session.commit()
        # Авто-сповіщення клієнту
        await send_msg(problem.user_id, f"🔧 До вашої заявки '{problem.title}' призначено технічного майстра. Очікуйте на ремонт!")
        
    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.post("/problem/{problem_id}/respond")
async def respond_problem(
    problem_id: int,
    message: str = Form(),
    current_user: tuple = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    admin_id, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403)

    new_response = AdminResponse(message=message, admin_id=admin_id, problem_id=problem_id)
    session.add(new_response)

    # Отримуємо заявку, щоб змінити її статус та дізнатися ID користувача для бота
    prob_res = await session.execute(select(Problem).filter(Problem.id == problem_id))
    problem = prob_res.scalars().first()
    if problem:
        problem.status = "Є відповідь"
        session.add(problem)
        await session.commit()
        # Авто-сповіщення клієнту
        await send_msg(problem.user_id, f"💬 Адміністратор залишив повідомлення до вашої заявки '{problem.title}':\n\n{message}")
    else:
        await session.commit()

    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.post("/problem/{problem_id}/close")
async def close_problem(
    problem_id: int,
    work_done: str = Form(),
    parts_used: str = Form(None),
    warranty_info: str = Form(),
    current_user: tuple = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    _, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403)

    res = await session.execute(select(Problem).filter(Problem.id == problem_id))
    problem = res.scalars().first()
    if problem:
        problem.status = "Завершений"
        record = ServiceRecord(
            work_done=work_done,
            parts_used=parts_used or "",
            warranty_info=warranty_info,
            problem_id=problem_id
        )
        session.add(record)
        session.add(problem)
        await session.commit()
        await send_msg(problem.user_id, f"✅ Ремонт завершено!\n\n🛠 Пристрій: {problem.title}\n🔧 Виконано: {work_done}\n📜 Гарантія: {warranty_info}")

    return RedirectResponse(url="/admin/dashboard", status_code=303)

@router.post("/problem/{problem_id}/take")
async def take_problem(problem_id: int, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    admin_id, role = current_user
    if role != "admin":
        raise HTTPException(status_code=403)

    res = await session.execute(select(Problem).filter(Problem.id == problem_id))
    problem = res.scalars().first()
    if problem:
        problem.admin_id = admin_id
        problem.status = "В обробці"
        await session.commit()
    return RedirectResponse(url="/admin/dashboard", status_code=303)