from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from src.database.models import Review, Exchange, ExchangeStatus
from src.schemas import ReviewCreate

async def get_reviews(db: Session, skip: int = 0, limit: int = 100, user_id: Optional[int] = None) -> List[Review]:
    query = db.query(Review)

    if user_id:
        query = query.filter(Review.reviewed_id == user_id)

    return query.offset(skip).limit(limit).all()

async def get_review(db: Session, review_id: int) -> Optional[Review]:
    return db.query(Review).filter(Review.id == review_id).first()

async def create_review(db: Session, review: ReviewCreate, reviewer_id: int) -> Optional[Review]:
    exchange = db.query(Exchange).filter(Exchange.id == review.exchange_id).first()

    if not exchange or exchange.status != ExchangeStatus.completed.value:
        return None

    if reviewer_id not in [exchange.sender_id, exchange.receiver_id]:
        return None

    reviewed_id = exchange.receiver_id if reviewer_id == exchange.sender_id else exchange.sender_id

    existing_review = db.query(Review).filter(
        Review.exchange_id == review.exchange_id,
        Review.reviewer_id == reviewer_id
    ).first()

    if existing_review:
        return None

    db_review = Review(
        exchange_id=review.exchange_id,
        reviewer_id=reviewer_id,
        reviewed_id=reviewed_id,
        rating=review.rating,
        comment=review.comment
    )

    db.add(db_review)
    db.commit()
    db.refresh(db_review)
    return db_review

async def get_user_reviews(db: Session, user_id: int) -> List[Review]:
    return db.query(Review).filter(Review.reviewed_id == user_id).all()

async def get_user_rating(db: Session, user_id: int) -> Optional[dict]:
    result = db.query(
        func.avg(Review.rating).label('average_rating'),
        func.count(Review.id).label('total_reviews')
    ).filter(Review.reviewed_id == user_id).first()

    if result and result.total_reviews > 0:
        return {
            "user_id": user_id,
            "average_rating": round(float(result.average_rating), 2),
            "total_reviews": result.total_reviews
        }

    return {
        "user_id": user_id,
        "average_rating": 0,
        "total_reviews": 0
    }