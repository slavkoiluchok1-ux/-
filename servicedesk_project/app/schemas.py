from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# Юзер
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    is_admin: bool
    
    class Config:
        from_attributes = True


# Проблема
class ProblemBase(BaseModel):
    title: str
    description: str

class ProblemCreate(ProblemBase):
    pass

class ProblemResponse(ProblemBase):
    id: int
    date_created: datetime
    image_url: Optional[str] = None
    status: str
    user_id: int
    admin_id: Optional[int] = None

    class Config:
        from_attributes = True


# Відповідь
class AdminResponseBase(BaseModel):
    message: str

class AdminResponseCreate(AdminResponseBase):
    problem_id: int

class AdminResponseSchema(AdminResponseBase):
    id: int
    date_responded: datetime
    admin_id: int
    problem_id: int

    class Config:
        from_attributes = True


# Талон
class ServiceRecordBase(BaseModel):
    work_done: str
    parts_used: Optional[str] = None
    warranty_info: str

class ServiceRecordCreate(ServiceRecordBase):
    problem_id: int

class ServiceRecordSchema(ServiceRecordBase):
    id: int
    date_completed: datetime
    problem_id: int

    class Config:
        from_attributes = True