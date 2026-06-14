from fastapi import APIRouter, Depends, Request, Form, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timedelta
import jwt
import bcrypt

from app.database import get_session, settings
from app.models import User
from app.security import get_current_user_optional

router = APIRouter(tags=["Auth"])
templates = Jinja2Templates(directory="templates")

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, current_user = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/admin/dashboard" if current_user.role == "admin" else "/worker/dashboard" if current_user.role == "worker" else "/client/dashboard", status_code=302)
    return templates.TemplateResponse(request, "register.html")

@router.post("/register")
async def register_user(
    request: Request,
    username: str = Form(),
    email: str = Form(),
    password: str = Form(),
    session: AsyncSession = Depends(get_session)
):
    new_user = User(username=username, email=email)
    new_user.set_password(password)
    session.add(new_user)
    await session.commit()
    return templates.TemplateResponse(request, "register.html", {"message": "Акаунт створено!"})

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, current_user = Depends(get_current_user_optional)):
    if current_user:
        return RedirectResponse(url="/admin/dashboard" if current_user.role == "admin" else "/worker/dashboard" if current_user.role == "worker" else "/client/dashboard", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": error})

@router.post("/login")
async def login_user(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session)
):
    res = await session.execute(select(User).filter(User.username == form_data.username))
    user = res.scalars().first()

    if not user or not bcrypt.checkpw(form_data.password.encode(), user.password.encode()):
        return RedirectResponse(url="/login?error=Невірний логін або пароль", status_code=302)

    token_data = {
        "user_id": user.id,
        "role": user.role,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    token = jwt.encode(token_data, settings.SECRET_KEY, algorithm="HS256")

    if user.role == "admin":
        url = "/admin/dashboard"
    elif user.role == "worker":
        url = "/worker/dashboard"
    else:
        url = "/client/dashboard"

    redirect = RedirectResponse(url=url, status_code=302)
    redirect.set_cookie(key="access_token", value=token, httponly=True, max_age=86400, samesite="lax")
    return redirect

@router.post("/logout")
async def logout():
    redirect = RedirectResponse(url="/", status_code=302)
    redirect.delete_cookie("access_token")
    return redirect

@router.get("/logout")
async def logout_get():
    redirect = RedirectResponse(url="/", status_code=302)
    redirect.delete_cookie("access_token")
    return redirect