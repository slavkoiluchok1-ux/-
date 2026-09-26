from sqlalchemy.orm import Session
from src.database.models import Exchange
from src.schemas import ExchangeCreate

async def create_exchange(db: Session, exchange: ExchangeCreate, sender_id: int):
    db_exchange = Exchange(**exchange.model_dump(), sender_id=sender_id)
    db.add(db_exchange)
    db.commit()
    db.refresh(db_exchange)
    return db_exchange

async def get_user_exchanges(db: Session, user_id: int):
    return db.query(Exchange).filter(
        (Exchange.sender_id == user_id) | (Exchange.receiver_id == user_id)
    ).all()