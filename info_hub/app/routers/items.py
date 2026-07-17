from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.models import Item

router = APIRouter(
    prefix="/items",
    tags=["items"],
)

@router.get("/")
def get_items(
    limit: int = Query(10, description="The number of items to return."),
    db=Depends(get_db)):
    return db.get_item()[:limit]

@router.post("/")
def create_item(item: Item):
    return item