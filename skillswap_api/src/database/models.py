from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table, Enum, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from src.database.db import Base
import enum

class SkillLevel(str, enum.Enum):
    beginner = "beginner"
    intermediate = "intermediate"
    advanced = "advanced"
    expert = "expert"

class ExchangeStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    completed = "completed"
    cancelled = "cancelled"

skill_user_association = Table(
    'skill_user',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('skill_id', Integer, ForeignKey('skills.id'))
)

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    skills = relationship("Skill", back_populates="category")

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    full_name = Column(String, nullable=True)
    bio = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    skills = relationship("Skill", secondary=skill_user_association, back_populates="users")

class Skill(Base):
    __tablename__ = "skills"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    category_id = Column(Integer, ForeignKey("categories.id"))
    level = Column(Enum(SkillLevel))
    can_teach = Column(Boolean, default=False)
    want_learn = Column(Boolean, default=False)
    users = relationship("User", secondary=skill_user_association, back_populates="skills")
    category = relationship("Category", back_populates="skills")

class Exchange(Base):
    __tablename__ = "exchanges"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    skill_id = Column(Integer, ForeignKey("skills.id"))
    message = Column(String, nullable=True)
    status = Column(Enum(ExchangeStatus), default=ExchangeStatus.pending)
    created_at = Column(DateTime, default=func.now())