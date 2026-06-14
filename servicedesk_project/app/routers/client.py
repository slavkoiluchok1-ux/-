from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import os
import uuid
import random
import string

from app.database import get_session
from app.models import Problem, ServiceRecord, Users_in_telegram  
from app.security import get_current_user, get_current_user_optional

router = APIRouter(prefix="/client", tags=["Client"])
templates = Jinja2Templates(directory="templates")
UPLOAD_DIR = "static/uploads"

@router.get("/dashboard", response_class=HTMLResponse)
async def client_dashboard(
    request: Request, 
    current_user: tuple = Depends(get_current_user), 
    db_user = Depends(get_current_user_optional), 
    session: AsyncSession = Depends(get_session)
):
    user_id, _ = current_user
    
    # Отримуємо заявки користувача
    res = await session.execute(select(Problem).filter(Problem.user_id == user_id))
    problems = res.scalars().all()
    
    # Перевіряємо статус Telegram-бота
    tg_res = await session.execute(
        select(Users_in_telegram).filter(Users_in_telegram.user_in_site == user_id)
    )
    tg_user = tg_res.scalars().first()
    
    is_tg_linked = False
    tg_code = ""
    
    # Якщо бот уже успішно прив'язаний
    if tg_user and tg_user.user_tg_id:
        is_tg_linked = True
    else:
        # Якщо ні — показуємо постійний простий код на основі ID
        tg_code = f"SD-{user_id}"

    return templates.TemplateResponse(
        request, 
        "dashboard_client.html", 
        {
            "problems": problems, 
            "user": db_user,
            "tg_code": tg_code, 
            "is_tg_linked": is_tg_linked 
        }
    )

@router.post("/problem/create")
async def create_problem(
    title: str = Form(),
    description: str = Form(),
    file: UploadFile = File(None),
    current_user: tuple = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    user_id, _ = current_user
    filename = None

    if file and file.filename:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        filename = f"{uuid.uuid4()}_{file.filename}"
        with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
            f.write(await file.read())

    new_problem = Problem(
        title=title,
        description=description,
        image_url=filename,
        user_id=user_id
    )
    session.add(new_problem)
    await session.commit()
    return RedirectResponse(url="/client/dashboard", status_code=303)

@router.get("/problem/{problem_id}", response_class=HTMLResponse)
async def view_order_details(
    problem_id: int, 
    request: Request, 
    current_user: tuple = Depends(get_current_user), 
    db_user = Depends(get_current_user_optional), 
    session: AsyncSession = Depends(get_session)
):
    user_id, _ = current_user
    res = await session.execute(select(Problem).filter(Problem.id == problem_id, Problem.user_id == user_id))
    problem = res.scalars().first()
    
    if not problem:
        raise HTTPException(status_code=404, detail="Замовлення не знайдено або доступ обмежено")
        
    record_res = await session.execute(select(ServiceRecord).filter(ServiceRecord.problem_id == problem_id))
    service_record = record_res.scalars().first()
        
    return templates.TemplateResponse(
        request, 
        "order_details.html", 
        {"problem": problem, "user": db_user, "record": service_record}
    )