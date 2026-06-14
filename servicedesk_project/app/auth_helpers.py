from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models import AdminResponse, User


def resolve_role(user: User) -> str:
    if user.role == "owner":
        return "owner"
    if user.is_admin or user.role == "admin":
        return "admin"
    if user.is_worker and user.role == "worker":
        return "worker"
    return "user"


async def unique_username(session: AsyncSession, base_name: str) -> str:
    name = base_name or "worker"
    counter = 1
    while True:
        result = await session.execute(select(User).filter(User.username == name))
        if not result.scalars().first():
            return name
        name = f"{base_name}{counter}"
        counter += 1


async def upsert_admin_response(
    session: AsyncSession,
    problem_id: int,
    admin_id: int,
    message: str,
) -> AdminResponse:
    result = await session.execute(
        select(AdminResponse).filter(AdminResponse.problem_id == problem_id)
    )
    answer = result.scalars().first()
    if answer:
        answer.message = message
        answer.admin_id = admin_id
        answer.is_read = False
    else:
        answer = AdminResponse(
            message=message,
            admin_id=admin_id,
            problem_id=problem_id,
            is_read=False,
        )
        session.add(answer)
    return answer
