from fastapi import APIRouter, Depends
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.categories import CATEGORY_NAME_SLUGS
from app.database import get_db
from app.models.category import Category
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(db: Session = Depends(get_db)) -> list[Category]:
    category_order = case(
        {slug: index for index, (_, slug) in enumerate(CATEGORY_NAME_SLUGS)},
        value=Category.slug,
        else_=len(CATEGORY_NAME_SLUGS),
    )
    return list(db.scalars(select(Category).order_by(category_order)))
