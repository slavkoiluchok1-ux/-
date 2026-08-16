from pydantic import BaseModel

class ComplaintCreate(BaseModel):
    title: str
    text: str

class ComplaintResponse(ComplaintCreate):
    id: int
    user_id: int
    status: str

    class Config:
        from_attributes = True
