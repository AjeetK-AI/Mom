from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.categories import (
    CATEGORY_NAME_SLUGS,
    CATEGORY_NAMES,
    LEGACY_POST_CATEGORY_SLUG,
)
from app.database import Base
from app.main import initialize_database
from app.models.category import Category
from app.models.post import Post, PostStatus
from app.routes.categories import list_categories


def test_initialize_database_migrates_legacy_posts_and_is_repeatable(
    monkeypatch,
) -> None:
    import app.main as main

    engine = create_engine("sqlite://")
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    with factory() as db:
        old_category = Category(name="Education", slug="education")
        existing_category = Category(name="Nutrition Notes", slug="nutrition-notes")
        db.add_all([old_category, existing_category])
        db.flush()
        old_category_id = old_category.id
        existing_category_id = existing_category.id
        db.add_all(
            [
                Post(
                    title="Legacy published",
                    slug="legacy-published",
                    content="Keep this content",
                    category_id=old_category_id,
                    status=PostStatus.PUBLISHED,
                ),
                Post(
                    title="Legacy draft",
                    slug="legacy-draft",
                    content="Keep this draft",
                    category_id=old_category_id,
                    status=PostStatus.DRAFT,
                ),
                Post(
                    title="Uncategorized draft",
                    slug="uncategorized-draft",
                    content="Still uncategorized",
                    category_id=None,
                    status=PostStatus.DRAFT,
                ),
                Post(
                    title="Already current",
                    slug="already-current",
                    content="Keep current assignment",
                    category_id=existing_category_id,
                    status=PostStatus.PUBLISHED,
                ),
            ]
        )
        db.commit()

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", factory)

    initialize_database()
    initialize_database()

    with factory() as db:
        categories = list_categories(db)
        assert {(category.name, category.slug) for category in categories} == set(
            CATEGORY_NAME_SLUGS
        )
        assert [category.name for category in categories] == list(CATEGORY_NAMES)
        fallback_id = db.scalar(
            select(Category.id).where(
                Category.slug == LEGACY_POST_CATEGORY_SLUG
            )
        )
        assert fallback_id is not None

        posts = {post.slug: post for post in db.scalars(select(Post))}
        assert posts["legacy-published"].category_id == fallback_id
        assert posts["legacy-published"].status == PostStatus.PUBLISHED
        assert posts["legacy-published"].content == "Keep this content"
        assert posts["legacy-draft"].category_id == fallback_id
        assert posts["legacy-draft"].status == PostStatus.DRAFT
        assert posts["uncategorized-draft"].category_id is None
        assert posts["already-current"].category_id == existing_category_id
