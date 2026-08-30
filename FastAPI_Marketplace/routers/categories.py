from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from dependencies import get_current_admin_user
from models import Category, User
from schemas import CategoryCreate, CategoryOut, CategoryUpdate

router = APIRouter(prefix="/api/v1", tags=["categories"])


async def _serialize_category(category: Category) -> dict:
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "icon": category.icon,
        "parent_id": category.parent_id,
        "children": [
            await _serialize_category(child) for child in sorted(category.children, key=lambda item: item.name.lower())
        ],
    }


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Category)
        .where(Category.parent_id.is_(None))
        .options(selectinload(Category.children))
        .order_by(Category.name.asc())
    )
    result = await db.execute(stmt)
    roots = result.scalars().all()

    serialized = []
    for category in roots:
        serialized.append(CategoryOut.model_validate(await _serialize_category(category)))
    return serialized


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    if payload.parent_id is not None:
        parent = await db.get(Category, payload.parent_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Батьківську категорію не знайдено")

    category = Category(
        name=payload.name.strip(),
        slug=payload.slug.strip().lower(),
        icon=payload.icon.strip() if payload.icon else None,
        parent_id=payload.parent_id,
    )

    db.add(category)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Категорія з таким ім'ям або slug вже існує")

    await db.refresh(category)
    return CategoryOut.model_validate(await _serialize_category(category))


@router.put("/categories/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Категорію не знайдено")

    if payload.parent_id is not None and payload.parent_id == category.id:
        raise HTTPException(status_code=400, detail="Категорія не може бути батьківською сама для себе")

    if payload.parent_id is not None:
        parent = await db.get(Category, payload.parent_id)
        if parent is None:
            raise HTTPException(status_code=404, detail="Батьківську категорію не знайдено")

    if payload.name is not None:
        category.name = payload.name.strip()
    if payload.slug is not None:
        category.slug = payload.slug.strip().lower()
    if payload.icon is not None:
        category.icon = payload.icon.strip() or None
    if payload.parent_id is not None:
        category.parent_id = payload.parent_id

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Категорія з таким ім'ям або slug вже існує")

    await db.refresh(category)
    return CategoryOut.model_validate(await _serialize_category(category))


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    category = await db.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Категорію не знайдено")

    await db.delete(category)
    await db.commit()
