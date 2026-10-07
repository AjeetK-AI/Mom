import re
import unicodedata
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.post import Post, PostStatus
from app.schemas.post import PostCreate, PostUpdate


def create_article(db: Session, payload: PostCreate) -> Post:
    values = payload.model_dump()
    _validate_category(db, values["category_id"])
    values["featured_image_url"] = (
        str(values["featured_image_url"]) if values["featured_image_url"] else None
    )
    if values["status"] == PostStatus.PUBLISHED and values["published_at"] is None:
        values["published_at"] = datetime.now(UTC).replace(tzinfo=None)
    elif values["published_at"] is not None:
        values["published_at"] = _as_utc_naive(values["published_at"])
    post = Post(**values)
    db.add(post)
    db.flush()
    return post


def create_draft(
    db: Session,
    *,
    title: str,
    content: str,
    slug_seed: str,
    telegram_file_id: str | None = None,
    featured_image_url: str | None = None,
) -> Post:
    slug = generate_unique_slug(db, slug_seed)
    post = Post(
        title=title,
        slug=slug,
        content=content,
        summary=None,
        category_id=None,
        featured_image_url=featured_image_url,
        telegram_file_id=telegram_file_id,
        status=PostStatus.DRAFT,
    )
    db.add(post)
    db.flush()
    return post


def update_article(db: Session, post_id: int, payload: PostUpdate) -> Post:
    post = db.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Article not found")

    changes = payload.model_dump(exclude_unset=True)
    if "category_id" in changes:
        _validate_category(db, changes["category_id"])
    if "slug" in changes:
        existing_post = db.scalar(select(Post).where(Post.slug == changes["slug"]))
        if existing_post is not None and existing_post.id != post_id:
            raise HTTPException(status_code=409, detail="An article with this slug already exists")
    if "featured_image_url" in changes:
        changes["featured_image_url"] = (
            str(changes["featured_image_url"]) if changes["featured_image_url"] else None
        )
    if changes.get("published_at") is not None:
        changes["published_at"] = _as_utc_naive(changes["published_at"])

    for field_name, value in changes.items():
        setattr(post, field_name, value)
    if post.status == PostStatus.PUBLISHED and post.published_at is None:
        post.published_at = datetime.now(UTC).replace(tzinfo=None)
    db.flush()
    return post


def generate_unique_slug(db: Session, slug_seed: str) -> str:
    base_slug = _slugify(slug_seed) or "new-article"
    base_slug = base_slug[:220].rstrip("-") or "new-article"
    slug = base_slug
    suffix = 2
    while db.scalar(select(Post.id).where(Post.slug == slug)) is not None:
        suffix_text = f"-{suffix}"
        slug = f"{base_slug[:255 - len(suffix_text)].rstrip('-')}{suffix_text}"
        suffix += 1
    return slug


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_value)).strip("-")


def _validate_category(db: Session, category_id: int | None) -> None:
    if category_id is not None and db.get(Category, category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")


def _as_utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
