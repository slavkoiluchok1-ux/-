from datetime import datetime, timezone

import bcrypt
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, index=True)
    password = Column(String(100))
    email = Column(String(100), unique=True, index=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String(20), default="user")
    display_name = Column(String(100), nullable=True)
    initial_name = Column(String(50), nullable=True)
    phone = Column(String(50), nullable=True)
    profile_photo = Column(String(250), nullable=True)
    is_worker = Column(Boolean, default=False)
    position = Column(String(50), nullable=True)
    position_level = Column(Integer, default=1)
    bio = Column(Text, nullable=True)

    problems = relationship("Problem", foreign_keys="[Problem.user_id]", back_populates="user")
    assigned_problems = relationship("Problem", foreign_keys="[Problem.admin_id]", back_populates="admin")
    worker_problems = relationship("Problem", foreign_keys="[Problem.worker_id]", back_populates="worker")
    responses = relationship("AdminResponse", back_populates="admin")

    def set_password(self, raw_password: str):
        hashed = bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt())
        self.password = hashed.decode("utf-8")

    def verify_password(self, raw_password: str) -> bool:
        return bcrypt.checkpw(raw_password.encode("utf-8"), self.password.encode("utf-8"))


class Problem(Base):
    __tablename__ = "problems"
    id = Column(Integer, primary_key=True)
    title = Column(String(250))
    description = Column(String(1000))
    date_created = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))
    image_url = Column(String(250), nullable=True)
    status = Column(String(250), default="В обробці")
    desired_date = Column(String(50), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(100), nullable=True)
    contact_other = Column(String(100), nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"))
    admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    worker_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", foreign_keys=[user_id], back_populates="problems")
    admin = relationship("User", foreign_keys=[admin_id], back_populates="assigned_problems")
    worker = relationship("User", foreign_keys=[worker_id], back_populates="worker_problems")

    response = relationship("AdminResponse", back_populates="problem", uselist=False)
    service_record = relationship("ServiceRecord", back_populates="problem", uselist=False)
    messages = relationship("ProblemMessage", back_populates="problem", order_by="ProblemMessage.created_at")


class AdminResponse(Base):
    __tablename__ = "admin_responses"
    id = Column(Integer, primary_key=True)
    message = Column(String(1000))
    date_responded = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))
    is_read = Column(Boolean, default=False)

    admin_id = Column(Integer, ForeignKey("users.id"))
    problem_id = Column(Integer, ForeignKey("problems.id"))

    admin = relationship("User", back_populates="responses")
    problem = relationship("Problem", back_populates="response")


class ServiceRecord(Base):
    __tablename__ = "service_records"
    id = Column(Integer, primary_key=True)
    work_done = Column(String(1000))
    date_completed = Column(DateTime(timezone=True), server_default=func.now())
    parts_used = Column(String(1000), nullable=True)
    warranty_info = Column(String(1000), nullable=True)

    problem_id = Column(Integer, ForeignKey("problems.id"))

    problem = relationship("Problem", back_populates="service_record")


class Users_in_telegram(Base):
    __tablename__ = "users_in_telegram"
    id = Column(Integer, primary_key=True)
    tg_code = Column(String(100), nullable=True)
    user_tg_id = Column(String(50), nullable=True)
    verify_code = Column(String(10), nullable=True)
    verify_chat_id = Column(String(50), nullable=True)
    user_in_site = Column(Integer, ForeignKey("users.id"))
    date_created = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))


class ProblemMessage(Base):
    __tablename__ = "problem_messages"
    id = Column(Integer, primary_key=True)
    problem_id = Column(Integer, ForeignKey("problems.id"), nullable=False)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sender_name = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))

    problem = relationship("Problem", back_populates="messages")


class SupportRequest(Base):
    __tablename__ = "support_requests"
    id = Column(Integer, primary_key=True)
    title = Column(String(250), nullable=False)
    message = Column(Text, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    contact_phone = Column(String(50), nullable=True)
    contact_email = Column(String(100), nullable=True)
    contact_other = Column(String(100), nullable=True)
    status = Column(String(50), default="Нова")
    response_message = Column(Text, nullable=True)
    date_created = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sender_name = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))


class WorkerApplication(Base):
    __tablename__ = "worker_applications"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    phone = Column(String(50), nullable=False)
    message = Column(Text, nullable=True)
    contact_other = Column(String(100), nullable=True)
    status = Column(String(50), default="Очікує")
    date_created = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))


class WorkerAction(Base):
    __tablename__ = "worker_actions"
    id = Column(Integer, primary_key=True)
    origin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    target_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action_type = Column(String(50), nullable=False)
    reason = Column(Text, nullable=True)
    status = Column(String(50), default="Очікує")
    reviewed_by = Column(Integer, nullable=True)
    date_created = Column(DateTime(timezone=True), server_default=func.now(), default=lambda: datetime.now(timezone.utc))
