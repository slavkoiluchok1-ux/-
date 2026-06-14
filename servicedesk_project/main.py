import asyncio
import os
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import (Cookie, Depends, FastAPI, File, Form, HTTPException,
                     Request, Response, UploadFile)
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.auth_helpers import resolve_role, unique_username, upsert_admin_response
from app.bot.tg_bot import send_msg
from app.bot.tg_bot import start as start_tg_bot
from app.database import Base, async_session, engine, get_session, settings
from app.migrations import migrate_schema
from app.models import (AdminResponse, ChatMessage, Problem, ProblemMessage,
                        ServiceRecord, SupportRequest, User, Users_in_telegram,
                        WorkerApplication)

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

app = FastAPI()

os.makedirs("static/user_problem_image", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
templates = Jinja2Templates(directory='templates')


def _format_datetime(value):
    if value is None:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d.%m.%Y %H:%M")
    return str(value)


templates.env.filters["format_dt"] = _format_datetime


def _user_from_token(access_token: str | None):
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        role = payload.get("role")
        if user_id is None or role is None:
            return None
        if role == "client":
            role = "user"
        return {"id": user_id, "role": role}
    except jwt.PyJWTError:
        return None


@app.middleware("http")
async def attach_user_middleware(request: Request, call_next):
    token_user = _user_from_token(request.cookies.get("access_token"))
    request.state.user = None
    if token_user:
        async with async_session() as session:
            result = await session.execute(select(User).filter_by(id=token_user["id"]))
            db_user = result.scalars().first()
            if db_user:
                request.state.user = {"id": db_user.id, "role": resolve_role(db_user)}
            else:
                request.state.user = token_user
    response = await call_next(request)
    return response


def render(request: Request, name: str, context: dict | None = None, status_code: int = 200):
    ctx = dict(context or {})
    if "user" not in ctx:
        ctx["user"] = getattr(request.state, "user", None)
    return templates.TemplateResponse(request=request, name=name, context=ctx, status_code=status_code)


async def ensure_tg_record(session: AsyncSession, user_id: int):
    res = await session.execute(
        select(Users_in_telegram).filter(Users_in_telegram.user_in_site == user_id)
    )
    tg_user = res.scalars().first()
    if not tg_user:
        session.add(Users_in_telegram(user_in_site=user_id, tg_code=f"SD-{user_id}"))
        await session.commit()


@app.on_event("startup")
async def on_startup():
    await init_db()

    async def start_bot_delayed():
        await asyncio.sleep(1)
        await start_tg_bot()

    asyncio.create_task(start_bot_delayed())
    print("Бот успішно запущений у фоновому режимі!")

@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.method == "GET":
        accept = request.headers.get("accept", "")
        if "text/html" in accept:
            return RedirectResponse(
                url="/login?error=Будь ласка, увійдіть в систему",
                status_code=302,
            )
    if exc.status_code in [401, 403]:
        return render(
            request,
            "unauthorized.html",
            {"detail": exc.detail},
            status_code=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

async def get_current_user(
    access_token: str = Cookie(None),
    session: AsyncSession = Depends(get_session),
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Неавторизовано")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401)
        result = await session.execute(select(User).filter_by(id=user_id))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="Користувача не знайдено")
        return user.id, resolve_role(user)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Недійсний токен")


def worker_required(user_data: tuple = Depends(get_current_user)) -> bool:
    _, role = user_data
    if role != "worker":
        raise HTTPException(status_code=403, detail="Доступ лише для працівників")
    return True

async def get_current_user_optional(access_token: str = Cookie(None)):
    return _user_from_token(access_token)


def staff_required(user_data: tuple = Depends(get_current_user)) -> bool:
    _, role = user_data
    if role not in ("admin", "owner"):
        raise HTTPException(status_code=403, detail="Доступ лише для адміністраторів")
    return True


admin_required = staff_required

def owner_required(user_data: tuple = Depends(get_current_user)) -> bool:
    user_id, role = user_data
    if role != "owner":
        raise HTTPException(status_code=403, detail="Доступ лише для власника")
    return True

@app.get("/")
async def home(
    request: Request,
    current_user = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session)
):
    tg_code = ""
    is_tg_linked = False

    if current_user:
        if isinstance(current_user, tuple):
            user_id = current_user[0]
        elif isinstance(current_user, dict):
            user_id = current_user.get("id")
        else:
            user_id = getattr(current_user, "id", None)

        if user_id:
            tg_res = await session.execute(
                select(Users_in_telegram).filter(Users_in_telegram.user_in_site == user_id)
            )
            tg_user = tg_res.scalars().first()

            tg_code = f"SD-{user_id}"
            if tg_user and tg_user.user_tg_id:
                is_tg_linked = True

    user_context = None
    if current_user:
        if isinstance(current_user, dict):
            user_context = current_user
        elif isinstance(current_user, tuple):
            user_context = {"id": current_user[0], "role": current_user[1]}

    return render(
        request,
        "index.html",
        {
            "user": user_context,
            "tg_code": tg_code,
            "is_tg_linked": is_tg_linked,
        },
    )

@app.get('/support')
async def support_page(request: Request, current_user: dict = Depends(get_current_user_optional), session: AsyncSession = Depends(get_session)):
    if current_user and current_user.get("role") in ("admin", "owner"):
        return RedirectResponse(url="/admin/support_requests", status_code=302)
    support_requests = []
    if current_user:
        res = await session.execute(select(SupportRequest).filter_by(user_id=current_user['id']).order_by(SupportRequest.date_created.desc()))
        support_requests = res.scalars().all()
    return render(request, 'support.html', {'support_requests': support_requests})

@app.post('/support')
async def submit_support(request: Request, title: str = Form(), message: str = Form(), contact_phone: str = Form(None), contact_email: str = Form(None), contact_other: str = Form(None), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user_id, role = current_user
    contact_phone = contact_phone.strip() if contact_phone else None
    contact_email = contact_email.strip() if contact_email else None
    contact_other = contact_other.strip() if contact_other else None
    if not any([contact_phone, contact_email, contact_other]):
        return templates.TemplateResponse(request=request, name='support.html', context={'error': 'Будь ласка, вкажіть хоча б один спосіб зв’язку.', 'user': {'id': user_id, 'role': role}, 'support_requests': []})

    new_support = SupportRequest(
        title=title,
        message=message,
        user_id=user_id,
        contact_phone=contact_phone,
        contact_email=contact_email,
        contact_other=contact_other,
        status='Нова',
        date_created=datetime.utcnow(),
    )
    session.add(new_support)
    await session.commit()
    return RedirectResponse(url='/support', status_code=303)

@app.get("/register")
async def create_user1(request: Request, current_user: dict = Depends(get_current_user_optional)):
    if current_user:
        if current_user['role'] == 'worker':
            return RedirectResponse(url='/worker/dashboard', status_code=302)
        if current_user['role'] in ('admin', 'owner'):
            return RedirectResponse(url='/admin/dashboard_stats', status_code=302)
        return RedirectResponse(url='/', status_code=302)
    return render(request, 'register.html')

@app.post("/register")
async def create_user2(
    request: Request,
    username: str = Form(),
    email: str = Form(),
    password: str = Form(),
    confirm_password: str = Form(),
    session: AsyncSession = Depends(get_session)
):
    if password != confirm_password:
        return templates.TemplateResponse(request=request, name='register.html', context={'error': 'Паролі не співпадають.', 'user': None})

    existing_user = await session.execute(select(User).filter((User.username == username) | (User.email == email)))
    if existing_user.scalars().first():
        return templates.TemplateResponse(request=request, name='register.html', context={'error': 'Такий логін або email вже існують.', 'user': None})

    new_user = User(username=username, email=email, display_name=username, initial_name=username, role='user')
    new_user.set_password(raw_password=password)
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    await ensure_tg_record(session, new_user.id)
    return render(request, 'register.html', {'message': 'Ви успішно створили акаунт!', 'user': None})

@app.get("/login")
async def aut_user1(request: Request, error: str = None, current_user: dict = Depends(get_current_user_optional)):
    if current_user:
        if current_user['role'] == 'worker':
            return RedirectResponse(url='/worker/dashboard', status_code=302)
        if current_user['role'] in ('admin', 'owner'):
            return RedirectResponse(url='/admin/dashboard_stats', status_code=302)
        return RedirectResponse(url='/', status_code=302)
    return render(request, 'login.html', {'error': error})

@app.post("/login")
async def aut_user2(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), session: AsyncSession = Depends(get_session)):
    user_select = await session.execute(select(User).filter(User.username == form_data.username))
    user = user_select.scalars().first()

    if not user or not bcrypt.checkpw(form_data.password.encode(), user.password.encode()):
        return RedirectResponse(url="/login/?error=Пароль або логін невірний, спробуйте ще раз", status_code=302)

    role_val = resolve_role(user)
    token_data = {
        "user_id": user.id,
        "role": role_val,
        "exp": datetime.utcnow() + timedelta(hours=24*3)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

    await ensure_tg_record(session, user.id)

    if role_val == "worker":
        redirect_url = "/worker/dashboard"
    elif role_val in ("admin", "owner"):
        redirect_url = "/admin/dashboard_stats"
    else:
        redirect_url = "/"
    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(key="access_token", value=token, httponly=True, max_age=60*60*24*3, samesite="lax")
    return response

@app.get('/add_my_problem')
async def add_problem1(request: Request, current_user: dict = Depends(get_current_user_optional)):
    if not current_user:
        return RedirectResponse(url="/login?error=Увійдіть, щоб створити заявку", status_code=302)
    return render(request, 'add_problem.html')

@app.post('/add_my_problem')
async def add_problem2(
    request: Request,
    title: str = Form(),
    description: str = Form(),
    desired_date: str = Form(None),
    contact_phone: str = Form(None),
    contact_email: str = Form(None),
    contact_other: str = Form(None),
    img: UploadFile = File(None),
    current_user: tuple = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    contact_phone = contact_phone.strip() if contact_phone else None
    contact_email = contact_email.strip() if contact_email else None
    contact_other = contact_other.strip() if contact_other else None

    if not any([contact_phone, contact_email, contact_other]):
        return templates.TemplateResponse(
            request=request,
            name='add_problem.html',
            context={
                'error': 'Будь ласка, вкажіть принаймні один варіант зв’язку: телефон, email або інший спосіб.',
                'user': {'id': current_user[0], 'role': 'admin' if current_user[1] == 'admin' else 'user'}
            }
        )

    img_path = None
    if img and img.filename:
        file_location = f"user_problem_image/{img.filename}"
        with open('static/' + file_location, "wb+") as f:
            f.write(await img.read())
        img_path = file_location

    new_problem = Problem(
        title=title,
        description=description,
        user_id=current_user[0],
        image_url=img_path,
        status="В обробці",
        desired_date=desired_date,
        contact_phone=contact_phone,
        contact_email=contact_email,
        contact_other=contact_other,
        date_created=datetime.utcnow(),
    )
    session.add(new_problem)
    await session.commit()
    return templates.TemplateResponse(request=request, name='add_problem.html', context={'message': f'Проблема: "{title}" записана!', 'user': {'id': current_user[0], 'role': 'admin' if current_user[1] == 'admin' else 'user'}})

@app.get('/apply_worker')
async def apply_worker_form(
    request: Request,
    current_user: dict = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    user_ctx = current_user
    if current_user:
        res = await session.execute(select(User).filter_by(id=current_user["id"]))
        db_user = res.scalars().first()
        if db_user:
            user_ctx = {
                "id": db_user.id,
                "role": current_user["role"],
                "display_name": db_user.display_name or db_user.username,
                "email": db_user.email,
                "phone": db_user.phone or "",
            }
    return render(request, 'apply_worker.html', {'user': user_ctx})

@app.post('/apply_worker')
async def apply_worker_submit(
    request: Request,
    name: str = Form(),
    email: str = Form(),
    phone: str = Form(),
    contact_other: str = Form(None),
    message: str = Form(None),
    current_user: dict = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session)
):
    phone = phone.strip() if phone else ""
    contact_other = contact_other.strip() if contact_other else None
    if not phone and not contact_other:
        return render(request, 'apply_worker.html', {
            'error': 'Вкажіть хоча б один спосіб зв’язку: телефон або інший варіант.',
        })
    application = WorkerApplication(
        name=name,
        email=email,
        phone=phone,
        contact_other=contact_other,
        message=message,
        status='Очікує',
        date_created=datetime.utcnow(),
    )
    session.add(application)
    await session.commit()
    return render(request, 'apply_worker.html', {
        'message': 'Ваша заявка отримана. Ми зв’яжемося з вами найближчим часом.',
    })

@app.get('/profile')
async def profile_page(request: Request, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user_id, role = current_user
    user_res = await session.execute(select(User).filter_by(id=user_id))
    user = user_res.scalars().first()
    return templates.TemplateResponse(
    request=request, 
    name='profile.html', 
    context={
        'user': {
            'id': user.id, 
            'role': role, 
            'username': user.username, 
            'display_name': getattr(user, 'display_name', user.username), 
            'initial_name': getattr(user, 'initial_name', ''), 
            'phone': getattr(user, 'phone', ''), 
            'email': user.email, 
            'position': getattr(user, 'position', ''), 
            'profile_photo': getattr(user, 'profile_photo', None), 
            'bio': getattr(user, 'bio', '')
        }
    }
)

@app.post('/profile')
async def update_profile(request: Request, display_name: str = Form(None), initial_name: str = Form(None), phone: str = Form(None), bio: str = Form(None), file: UploadFile = File(None), session: AsyncSession = Depends(get_session), current_user: tuple = Depends(get_current_user)):
    user_id, role = current_user
    user_res = await session.execute(select(User).filter_by(id=user_id))
    user = user_res.scalars().first()
    if user:
        new_display_name = display_name.strip() if display_name else user.display_name
        new_initial_name = initial_name.strip() if initial_name else user.initial_name
        if new_initial_name != user.initial_name:
            existing_user = await session.execute(select(User).filter(User.username == new_initial_name, User.id != user_id))
            if existing_user.scalars().first():
                return templates.TemplateResponse(
                    request=request,
                    name='profile.html',
                    context={
                        'error': 'Логін вже зайнятий. Виберіть інше початкове ім’я.',
                        'user': {
                            'id': user.id,
                            'role': role,
                            'username': user.username,
                            'display_name': new_display_name,
                            'initial_name': user.initial_name,
                            'phone': phone.strip() if phone else user.phone,
                            'email': user.email,
                            'position': user.position,
                            'profile_photo': user.profile_photo,
                            'bio': bio.strip() if bio else getattr(user, 'bio', '')
                        }
                    }
                )
        user.display_name = new_display_name
        user.initial_name = new_initial_name
        user.username = new_initial_name
        user.phone = phone.strip() if phone else None
        user.bio = bio.strip() if bio else None
        if file and file.filename:
            os.makedirs('static/profile_photos', exist_ok=True)
            filename = f"{user_id}_{file.filename}"
            file_path = f"profile_photos/{filename}"
            with open('static/' + file_path, 'wb+') as f:
                f.write(await file.read())
            user.profile_photo = file_path
        session.add(user)
        await session.commit()
    return RedirectResponse(url='/profile', status_code=303)

@app.get('/forum')
async def forum_page(request: Request, current_user: dict = Depends(get_current_user_optional), session: AsyncSession = Depends(get_session)):
    messages = []
    res = await session.execute(select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(100))
    msgs = list(reversed(res.scalars().all()))
    for msg in msgs:
        sender = None
        try:
            ures = await session.execute(select(User).filter_by(id=msg.sender_id))
            sender = ures.scalars().first()
        except Exception:
            sender = None
        role_label = 'Користувач'
        if sender:
            if getattr(sender, 'role', '') == 'owner':
                role_label = 'Власник'
            elif sender.is_admin:
                role_label = 'Адмін'
            elif sender.is_worker:
                role_label = f"Працівник ({getattr(sender, 'position', '')})"
        messages.append({'sender_name': msg.sender_name, 'message': msg.message, 'created_at': msg.created_at, 'role': role_label})
    return templates.TemplateResponse(request=request, name='forum.html', context={'user': current_user, 'messages': messages})

@app.post('/forum')
async def submit_forum_message(request: Request, message: str = Form(), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    user_id, role = current_user
    user_res = await session.execute(select(User).filter_by(id=user_id))
    user = user_res.scalars().first()
    if user:
        msg_text = message.strip() if message else ""
        if msg_text:
            chat = ChatMessage(sender_id=user_id, sender_name=user.display_name or user.username, message=msg_text, created_at=datetime.utcnow())
            session.add(chat)
            await session.commit()
    return RedirectResponse(url='/forum', status_code=303)

@app.get('/admin/workers')
async def admin_workers_page(request: Request, position: str = None, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    q = select(User).filter((User.is_worker == True) | (User.is_admin == True))
    if position:
        q = q.filter(User.position == position)
    res = await session.execute(q)
    workers = res.scalars().all()
    apps_res = await session.execute(select(WorkerApplication).filter_by(status='Очікує').order_by(WorkerApplication.date_created.desc()))
    applications = apps_res.scalars().all()
    return templates.TemplateResponse(request=request, name='admin_workers.html', context={'user': {'id': current_user[0], 'role': 'admin'}, 'workers': workers, 'applications': applications, 'position': position})

@app.post('/admin/workers/action')
async def admin_workers_action(request: Request, user_id: int = Form(...), action: str = Form(...), target_position: str = Form(None), session: AsyncSession = Depends(get_session), current_user: tuple = Depends(get_current_user), is_admin: bool = Depends(admin_required)):
    res = await session.execute(select(User).filter_by(id=user_id))
    worker = res.scalars().first()
    if worker:
        if action == 'fire':
            worker.is_worker = False
            worker.role = 'user'
            worker.position = 'початківець'
            worker.position_level = 1
        elif action == 'promote' and target_position:
            worker.position = target_position
            levels = {'початківець': 1, 'молодший': 2, 'старший': 3, 'головний': 4}
            worker.position_level = levels.get(target_position, worker.position_level)
        session.add(worker)
        await session.commit()
    return RedirectResponse(url='/admin/workers', status_code=303)

@app.get('/owner')
async def owner_page(request: Request, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_owner: bool = Depends(owner_required)):
    users_res = await session.execute(select(User))
    all_users = users_res.scalars().all()
    return templates.TemplateResponse(request=request, name='owner_dashboard.html', context={'user': {'id': current_user[0], 'role': current_user[1]}, 'all_users': all_users})

@app.post('/owner/action')
async def owner_action(request: Request, user_id: int = Form(...), action: str = Form(...), target_role: str = Form(None), session: AsyncSession = Depends(get_session), current_user: tuple = Depends(get_current_user), is_owner: bool = Depends(owner_required)):
    user_res = await session.execute(select(User).filter_by(id=user_id))
    u = user_res.scalars().first()
    if u:
        if action == 'set_role' and target_role:
            u.role = target_role
            if target_role == 'admin':
                u.is_admin = True
            else:
                u.is_admin = False
        elif action == 'fire':
            u.is_worker = False
            u.position = 'початківець'
            u.position_level = 1
        session.add(u)
        await session.commit()
    return RedirectResponse(url='/owner', status_code=303)

@app.post('/admin/applications/approve')
async def approve_worker_application(request: Request, application_id: int = Form(...), session: AsyncSession = Depends(get_session), current_user: tuple = Depends(get_current_user), is_admin: bool = Depends(admin_required)):
    res = await session.execute(select(WorkerApplication).filter_by(id=application_id))
    application = res.scalars().first()
    if not application:
        return RedirectResponse(url='/admin/workers', status_code=303)

    existing_user = await session.execute(select(User).filter_by(email=application.email))
    user = existing_user.scalars().first()
    if not user:
        base_login = (application.email.split('@')[0] if '@' in application.email else application.name).strip() or "worker"
        login_name = await unique_username(session, base_login)
        user = User(
            username=login_name,
            email=application.email,
            display_name=application.name,
            initial_name=login_name,
            phone=application.phone,
            is_worker=True,
            position='початківець',
            position_level=1,
            role='worker',
        )
        user.set_password(raw_password='worker123')
        session.add(user)
    else:
        user.is_worker = True
        user.position = 'початківець'
        user.position_level = 1
        user.role = 'worker'
        user.display_name = application.name or user.display_name
        user.phone = application.phone or user.phone
        session.add(user)

    application.status = 'Прийнято'
    session.add(application)
    await session.commit()
    return RedirectResponse(url='/admin/workers', status_code=303)

@app.post('/admin/applications/reject')
async def reject_worker_application(request: Request, application_id: int = Form(...), session: AsyncSession = Depends(get_session), current_user: tuple = Depends(get_current_user), is_admin: bool = Depends(admin_required)):
    res = await session.execute(select(WorkerApplication).filter_by(id=application_id))
    application = res.scalars().first()
    if application:
        application.status = 'Відхилено'
        session.add(application)
        await session.commit()
    return RedirectResponse(url='/admin/workers', status_code=303)

@app.get('/my_all_problems')
async def my_all_prblms(request: Request, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    all_problems = await session.execute(select(Problem).filter_by(user_id=current_user[0]))
    problems = all_problems.scalars().all()
    return templates.TemplateResponse(request=request, name='all_my_problems.html', context={'problems': problems, 'user': {'id': current_user[0], 'role': current_user[1]}})

@app.get('/check_message')
async def check_message(request: Request, id: int = None, problem_id: int = None, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    problem_key = id if id is not None else problem_id
    problem = None
    if problem_key is not None:
        result = await session.execute(select(Problem).filter_by(id=problem_key))
        problem = result.scalars().one_or_none()

    answer = None
    if problem:
        problem_answer = await session.execute(select(AdminResponse).filter_by(problem_id=problem_key))
        answer = problem_answer.scalars().one_or_none()
        if answer and not getattr(answer, 'is_read', False):
            answer.is_read = True
            await session.commit()

    chat_messages = []
    if problem:
        msgs_res = await session.execute(
            select(ProblemMessage).filter_by(problem_id=problem.id).order_by(ProblemMessage.created_at)
        )
        chat_messages = msgs_res.scalars().all()
    return render(request, 'check_message.html', {
        'problem': problem,
        'answer': answer,
        'chat_messages': chat_messages,
    })

@app.get('/new_problems')
async def user_problems(request: Request, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    new_problems = await session.execute(select(Problem).filter_by(status="В обробці"))
    problems = new_problems.scalars().all()
    return templates.TemplateResponse(request=request, name='all_problems.html', context={'problems': problems, 'user': {'id': current_user[0], 'role': 'admin'}})

@app.get('/problem')
async def user_problem(request: Request, problem_id: int = None, id: int = None, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    pid = problem_id if problem_id is not None else id
    problem = None
    if pid is not None:
        problem_res = await session.execute(select(Problem).filter_by(id=pid))
        problem = problem_res.scalars().first()
    return templates.TemplateResponse(request=request, name='problem_check.html', context={'problem': problem, 'user': {'id': current_user[0], 'role': 'admin'}})

@app.post('/problem')
async def take_problem(request: Request, current_user: tuple = Depends(get_current_user), id: int = Form(), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    problem = await session.execute(select(Problem).filter_by(id=id))
    problem = problem.scalar_one_or_none()
    if problem:
        problem.status = 'У роботі'
        problem.admin_id = current_user[0]
        session.add(problem)
        await session.commit()
    return templates.TemplateResponse(request=request, name='problem_check.html', context={'problem': problem, 'message': 'Заявку взято в роботу!', 'user': {'id': current_user[0], 'role': 'admin'}})

@app.get('/admin_problems')
async def admin_problems(request: Request, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    all_problems = await session.execute(select(Problem).order_by(Problem.date_created.desc()))
    problems = all_problems.scalars().all()
    return templates.TemplateResponse(request=request, name='admin_problems.html', context={'problems': problems, 'user': {'id': current_user[0], 'role': 'admin'}})

@app.get('/add_answer')
async def add_answer_page(problem_id: int, request: Request, current_user: tuple = Depends(get_current_user), is_admin: bool = Depends(admin_required)):
    return templates.TemplateResponse(request=request, name='add_answer.html', context={'id': problem_id, 'user': {'id': current_user[0], 'role': 'admin'}})

@app.post('/add_answer')
async def add_answer_logic(request: Request, problem_id: int = Form(), current_user: tuple = Depends(get_current_user), message: str = Form(), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    problem_res = await session.execute(select(Problem).filter_by(id=problem_id))
    problem = problem_res.scalars().one_or_none()
    if problem:
        await upsert_admin_response(session, problem_id, current_user[0], message)
        problem.status = 'Є відповідь'
        session.add(problem)
        await session.commit()
        await send_msg(problem.user_id, f"💬 Відповідь до заявки «{problem.title}»:\n\n{message}")
    referer = request.headers.get("referer", "")
    if "admin_problems" in referer:
        return RedirectResponse(url="/admin_problems", status_code=303)
    if "dashboard_stats" in referer:
        return RedirectResponse(url="/admin/dashboard_stats", status_code=303)
    return render(request, 'add_answer.html', {'message': 'Відповідь збережена!', 'id': problem_id})

async def _worker_active_problem(session: AsyncSession, worker_id: int):
    result = await session.execute(
        select(Problem).filter(
            Problem.worker_id == worker_id,
            Problem.status == 'У роботі',
        )
    )
    return result.scalars().first()


@app.get('/worker/dashboard')
async def worker_dashboard(
    request: Request,
    current_user: tuple = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    is_worker: bool = Depends(worker_required),
):
    user_id, _ = current_user
    error = request.query_params.get("error")
    active = await _worker_active_problem(session, user_id)
    available_res = await session.execute(
        select(Problem).filter(
            Problem.status == 'В обробці',
            Problem.worker_id.is_(None),
        ).order_by(Problem.date_created.desc())
    )
    available = available_res.scalars().all()
    chat_messages = []
    if active:
        msgs_res = await session.execute(
            select(ProblemMessage).filter_by(problem_id=active.id).order_by(ProblemMessage.created_at)
        )
        chat_messages = msgs_res.scalars().all()
    return render(request, 'worker_dashboard.html', {
        'active_problem': active,
        'available_problems': available,
        'chat_messages': chat_messages,
        'error': error,
    })


@app.post('/worker/problem/{problem_id}/take')
async def worker_take_problem(
    problem_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: tuple = Depends(get_current_user),
    is_worker: bool = Depends(worker_required),
):
    worker_id, _ = current_user
    active = await _worker_active_problem(session, worker_id)
    if active and active.id != problem_id:
        return RedirectResponse(
            url='/worker/dashboard?error=Закінчіть поточну заявку перед тим, як брати нову',
            status_code=303,
        )

    result = await session.execute(select(Problem).filter_by(id=problem_id))
    problem = result.scalars().first()
    if not problem or problem.status != 'В обробці' or problem.worker_id is not None:
        return RedirectResponse(url='/worker/dashboard', status_code=303)

    problem.worker_id = worker_id
    problem.status = 'У роботі'
    session.add(problem)
    await session.commit()
    await send_msg(problem.user_id, f"🔧 Вашу заявку «{problem.title}» взято в роботу майстром.")
    return RedirectResponse(url='/worker/dashboard', status_code=303)


@app.post('/worker/problem/{problem_id}/chat')
async def worker_send_chat_message(
    problem_id: int,
    message: str = Form(),
    session: AsyncSession = Depends(get_session),
    current_user: tuple = Depends(get_current_user),
    is_worker: bool = Depends(worker_required),
):
    worker_id, _ = current_user
    result = await session.execute(select(Problem).filter_by(id=problem_id, worker_id=worker_id))
    problem = result.scalars().first()
    if not problem:
        raise HTTPException(status_code=404, detail="Заявку не знайдено")

    worker_res = await session.execute(select(User).filter_by(id=worker_id))
    worker = worker_res.scalars().first()
    text = message.strip()
    if text:
        session.add(ProblemMessage(
            problem_id=problem_id,
            sender_id=worker_id,
            sender_name=worker.display_name or worker.username,
            message=text,
            created_at=datetime.utcnow(),
        ))
        await session.commit()
        await send_msg(problem.user_id, f"💬 Повідомлення від майстра по заявці «{problem.title}»:\n\n{text}")
    return RedirectResponse(url='/worker/dashboard', status_code=303)


@app.post('/worker/problem/{problem_id}/complete')
async def worker_complete_problem(
    problem_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: tuple = Depends(get_current_user),
    is_worker: bool = Depends(worker_required),
):
    worker_id, _ = current_user
    result = await session.execute(select(Problem).filter_by(id=problem_id, worker_id=worker_id))
    problem = result.scalars().first()
    if problem:
        problem.status = 'Завершено'
        session.add(problem)
        await session.commit()
        await send_msg(problem.user_id, f"✅ Заявку «{problem.title}» завершено майстром.")
    return RedirectResponse(url='/worker/dashboard', status_code=303)

@app.post('/delete_problem')
async def delete_problem(problem_id: int = Form(), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    res = await session.execute(select(Problem).filter_by(id=problem_id))
    problem = res.scalars().one_or_none()
    if problem:
        await session.delete(problem)
        await session.commit()
    return RedirectResponse(url="/admin/dashboard_stats", status_code=303)

@app.get('/admin/dashboard_stats')
async def global_admin_dashboard(request: Request, session: AsyncSession = Depends(get_session), current_user: tuple = Depends(get_current_user), is_admin: bool = Depends(admin_required)):
    res = await session.execute(
        select(Problem).options(selectinload(Problem.user)).order_by(Problem.date_created.desc())
    )
    all_problems = res.scalars().all()

    stats = {"В обробці": 0, "У роботі": 0, "Є відповідь": 0, "Завершено": 0}
    for p in all_problems:
        if p.status in stats:
            stats[p.status] += 1

    return render(request, 'dashboard_admin.html', {'problems': all_problems, 'stats': stats})


@app.get('/admin/support_requests')
async def admin_support_requests(
    request: Request,
    session: AsyncSession = Depends(get_session),
    current_user: tuple = Depends(get_current_user),
    is_admin: bool = Depends(admin_required),
):
    res = await session.execute(
        select(SupportRequest).order_by(SupportRequest.date_created.desc())
    )
    requests_list = res.scalars().all()
    enriched = []
    for req in requests_list:
        user_res = await session.execute(select(User).filter_by(id=req.user_id))
        author = user_res.scalars().first()
        enriched.append({
            "id": req.id,
            "title": req.title,
            "message": req.message,
            "user_id": req.user_id,
            "author_name": (author.display_name or author.username) if author else None,
            "contact_phone": req.contact_phone,
            "contact_email": req.contact_email,
            "contact_other": req.contact_other,
            "status": req.status,
            "response_message": req.response_message,
            "date_created": req.date_created,
        })
    return render(request, 'admin_support.html', {'support_requests': enriched})


@app.post('/admin/support/{request_id}/respond')
async def admin_support_respond(
    request_id: int,
    response_message: str = Form(),
    session: AsyncSession = Depends(get_session),
    current_user: tuple = Depends(get_current_user),
    is_admin: bool = Depends(admin_required),
):
    res = await session.execute(select(SupportRequest).filter_by(id=request_id))
    support_req = res.scalars().first()
    if support_req:
        support_req.response_message = response_message.strip()
        support_req.status = "Відповідено"
        session.add(support_req)
        await session.commit()
        await send_msg(
            support_req.user_id,
            f"📩 Відповідь на ваше звернення «{support_req.title}»:\n\n{response_message.strip()}",
        )
    return RedirectResponse(url="/admin/support_requests", status_code=303)

@app.post('/admin/problem/{problem_id}/take')
async def admin_take_problem(problem_id: int, current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    problem_res = await session.execute(select(Problem).filter_by(id=problem_id))
    problem = problem_res.scalars().one_or_none()
    if problem:
        problem.status = 'У роботі'
        problem.admin_id = current_user[0]
        session.add(problem)
        await session.commit()
        
        await send_msg(problem.user_id, f"🔔 Вашу заявку '{problem.title}' взято в роботу!")
        
    return RedirectResponse(url='/admin/dashboard_stats', status_code=303)

@app.post('/admin/problem/{problem_id}/respond')
async def admin_respond_problem(problem_id: int, message: str = Form(), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    problem_res = await session.execute(select(Problem).filter_by(id=problem_id))
    problem = problem_res.scalars().one_or_none()
    if problem:
        await upsert_admin_response(session, problem_id, current_user[0], message)
        problem.status = 'Є відповідь'
        session.add(problem)
        await session.commit()
        await send_msg(problem.user_id, f"💬 Майстер залишив повідомлення до заявки '{problem.title}':\n\n{message}")
    return RedirectResponse(url='/admin/dashboard_stats', status_code=303)

@app.post('/admin/problem/{problem_id}/close')
async def admin_close_problem(problem_id: int, work_done: str = Form(), parts_used: str = Form(None), warranty_info: str = Form(), current_user: tuple = Depends(get_current_user), session: AsyncSession = Depends(get_session), is_admin: bool = Depends(admin_required)):
    problem_res = await session.execute(select(Problem).filter_by(id=problem_id))
    problem = problem_res.scalars().one_or_none()
    if problem:
        record = ServiceRecord(problem_id=problem_id, work_done=work_done, parts_used=parts_used or '', warranty_info=warranty_info)
        session.add(record)
        problem.status = 'Завершено'
        session.add(problem)
        await session.commit()
        
        await send_msg(problem.user_id, f"✅ Вашу заявку '{problem.title}' успішно завершено!\n\n🛠 Виконані роботи: {work_done}\n📜 Гарантія: {warranty_info}")
        
    return RedirectResponse(url='/admin/dashboard_stats', status_code=303)

@app.get('/logout')
async def logout_get():
    response = RedirectResponse(url='/', status_code=302)
    response.delete_cookie('access_token')
    return response

@app.post("/logout")
def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Ви вийшли з системи"}

async def init_db():
    async with engine.begin() as conn:
        await migrate_schema(conn)

    async with async_session() as session:
        result = await session.execute(select(User).filter(User.username == "???"))
        admin_user = result.scalars().first()
        if not admin_user:
            admin_user = User(
                username="???",
                email="admin@example.com",
                display_name="???",
                initial_name="???",
                is_admin=True,
                role="admin",
            )
            admin_user.set_password(raw_password="0668320550")
            session.add(admin_user)
            await session.commit()

        owner_username = "\\\\"
        owner_res = await session.execute(select(User).filter(User.username == owner_username))
        owner = owner_res.scalars().first()
        if not owner:
            owner = User(
                username=owner_username,
                email="owner@example.com",
                display_name="Власник",
                initial_name=owner_username,
                is_admin=True,
                role="owner",
            )
            owner.set_password(raw_password="0668320550")
            session.add(owner)
            await session.commit()

        all_users_res = await session.execute(select(User))
        for u in all_users_res.scalars().all():
            changed = False
            if u.is_admin and u.role not in ("admin", "owner"):
                u.role = "admin"
                changed = True
            if u.role == "client":
                u.role = "user"
                changed = True
            if not u.is_worker and not u.is_admin and u.role not in ("admin", "owner"):
                if u.role != "user":
                    u.role = "user"
                    changed = True
            if changed:
                session.add(u)
        await session.commit()