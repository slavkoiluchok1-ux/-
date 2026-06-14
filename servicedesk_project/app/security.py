import jwt
from fastapi import Depends, HTTPException, Cookie
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_session, settings
from app.models import User

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = getattr(settings, "ALGORITHM", "HS256")

async def get_current_user(access_token: str = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизовано")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        role: str = payload.get("role")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Некоректний токен")
        return user_id, role
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Некоректний токен")

async def get_current_user_optional(access_token: str = Cookie(None), db: AsyncSession = Depends(get_session)):
    if not access_token:
        return None
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            return None
        
        result = await db.execute(select(User).filter(User.id == user_id))
        user = result.scalars().first()
        return user
    except Exception:
        return None