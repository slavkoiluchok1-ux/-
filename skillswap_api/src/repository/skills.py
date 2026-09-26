from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_
from src.database.models import Skill, User
from src.schemas import SkillCreate, SkillUpdate

async def get_skills(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    can_teach: Optional[bool] = None,
    want_learn: Optional[bool] = None,
    search: Optional[str] = None
) -> List[Skill]:
    query = db.query(Skill)

    if category:
        query = query.filter(Skill.category == category)
    if can_teach is not None:
        query = query.filter(Skill.can_teach == can_teach)
    if want_learn is not None:
        query = query.filter(Skill.want_learn == want_learn)
    if search:
        search_filter = f"%{search}%"
        query = query.filter(
            or_(
                Skill.title.ilike(search_filter),
                Skill.description.ilike(search_filter)
            )
        )

    return query.offset(skip).limit(limit).all()

async def get_skill(db: Session, skill_id: int) -> Optional[Skill]:
    return db.query(Skill).filter(Skill.id == skill_id).first()

async def create_skill(db: Session, skill: SkillCreate, user_id: int) -> Skill:
    db_skill = Skill(**skill.dict())
    db.add(db_skill)
    db.commit()
    db.refresh(db_skill)

    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.skills.append(db_skill)
        db.commit()

    return db_skill

async def update_skill(db: Session, skill_id: int, skill_update: SkillUpdate) -> Optional[Skill]:
    db_skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if db_skill:
        update_data = skill_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_skill, field, value)
        db.commit()
        db.refresh(db_skill)
    return db_skill

async def delete_skill(db: Session, skill_id: int) -> Optional[Skill]:
    db_skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if db_skill:
        db.delete(db_skill)
        db.commit()
    return db_skill

async def find_skill_matches(db: Session, skill_id: int) -> dict:
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        return {"matches": []}

    matches = []
    similar_skills = db.query(Skill).filter(
        Skill.id != skill_id,
        Skill.title.ilike(f"%{skill.title}%"),
        Skill.category == skill.category
    ).all()

    for other_skill in similar_skills:
        if skill.want_learn and other_skill.can_teach:
            matches.append({
                "type": "teacher",
                "skill": other_skill,
                "users": other_skill.users
            })
        elif skill.can_teach and other_skill.want_learn:
            matches.append({
                "type": "student",
                "skill": other_skill,
                "users": other_skill.users
            })

    return {
        "skill": skill,
        "matches_count": len(matches),
        "matches": matches
    }