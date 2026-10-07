from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TelegramUpdate(Base):
    __tablename__ = "telegram_updates"

    __table_args__ = (
        UniqueConstraint(
            "update_id",
            name="uq_telegram_updates_update_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    update_id: Mapped[int] = mapped_column(
        BIGINT,
        nullable=False,
    )

    post_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("posts.id", ondelete="SET NULL"),
        nullable=True,
    )

    processed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )