from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from src.database.models import Skill, skill_user_association, User, Exchange, ExchangeStatus

async def get_top_skills(db: Session, limit: int = 10):
    # Топ популярних навичок за кількістю користувачів
    return db.query(
        Skill.title, 
        func.count(skill_user_association.c.user_id).label('users_count')
    ).join(skill_user_association).group_by(Skill.id).order_by(desc('users_count')).limit(limit).all()

async def get_active_users(db: Session, limit: int = 10):
    # Топ користувачів за кількістю ініційованих обмінів
    return db.query(
        User.username, 
        func.count(Exchange.id).label('exchanges_count')
    ).join(Exchange, User.id == Exchange.sender_id).group_by(User.id).order_by(desc('exchanges_count')).limit(limit).all()

async def get_exchange_success_rate(db: Session):
    total = db.query(func.count(Exchange.id)).scalar() or 0
    if total == 0: return {"rate": 0, "total": 0}
    
    success = db.query(func.count(Exchange.id)).filter(Exchange.status == ExchangeStatus.completed).scalar() or 0
    return {
        "success_rate_percent": round((success / total) * 100, 2),
        "total_exchanges": total,
        "successful_exchanges": success
    }