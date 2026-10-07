from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLAlchemyEnum, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PostStatus(str, Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    featured_image_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[PostStatus] = mapped_column(
        SQLAlchemyEnum(
            PostStatus,
            name="post_status",
            values_callable=lambda enum_type: [member.value for member in enum_type],
        ),
        nullable=False,
        default=PostStatus.DRAFT,
        server_default=PostStatus.DRAFT.value,
        index=True,
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped["Category | None"] = relationship(back_populates="posts")
