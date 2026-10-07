from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.models.post import PostStatus
from app.schemas.category import CategoryResponse

SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


class PostFields(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=SLUG_PATTERN)
    content: str = Field(min_length=1)
    summary: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    featured_image_url: HttpUrl | None = Field(default=None, max_length=2048)
    status: PostStatus = PostStatus.DRAFT


class PostCreate(PostFields):
    published_at: datetime | None = None


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255, pattern=SLUG_PATTERN)
    content: str | None = Field(default=None, min_length=1)
    summary: str | None = None
    category_id: int | None = Field(default=None, gt=0)
    featured_image_url: HttpUrl | None = Field(default=None, max_length=2048)
    status: PostStatus | None = None
    published_at: datetime | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "PostUpdate":
        for field_name in ("title", "slug", "content", "status"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class PostResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    summary: str | None
    category: CategoryResponse | None
    featured_image_url: str | None
    telegram_file_id: str | None = None
    status: PostStatus
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PostListResponse(BaseModel):
    items: list[PostResponse]
    page: int
    limit: int
    total: int
    pages: int
