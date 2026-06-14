from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.bot.tg_bot import send_msg
from app.database import get_session
from app.models import Problem, ServiceRecord
from app.security import get_current_user, get_current_user_optional

router = APIRouter(prefix="/worker", tags=["Worker"])
templates = Jinja2Templates(directory="templates")

@router.get("/dashboard", response_class=HTMLResponse)
async def worker_dashboard(request: Request, current_user: tuple = Depends(get_current_user), db_user = Depends(get_current_user_optional), session: AsyncSession = Depends(get_session)):
    worker_id, role = current_user
    if role != "worker":
        raise HTTPException(status_code=403, detail="Ви не є зареєстрованим майстром")
        
    res = await session.execute(select(Problem).filter(Problem.worker_id == worker_id))
    my_tasks = res.scalars().all()
    return templates.TemplateResponse(request, "dashboard_worker.html", {"problems": my_tasks, "user": db_user})

@router.post("/problem/{problem_id}/status")
async def update_task_status(problem_id: int, status: str = Form(), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    worker_id, role = current_user
    if role != "worker":
        raise HTTPException(status_code=403)
        
    res = await session.execute(select(Problem).filter(Problem.id == problem_id, Problem.worker_id == worker_id))
    problem = res.scalars().first()
    if problem:
        problem.status = status
        await session.commit()
        await send_msg(problem.user_id, f"🔄 Статус вашої заявки '{problem.title}' змінено майстром на: {status}")
        
    return RedirectResponse(url="/worker/dashboard", status_code=303)