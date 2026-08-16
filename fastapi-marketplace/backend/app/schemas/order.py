from pydantic import BaseModel
from typing import List
from datetime import datetime

class OrderCreate(BaseModel):
    product_ids: List[int]

class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_price: float
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
