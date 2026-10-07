import hmac
import logging

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.categories import CATEGORY_NAMES
from app.config import Settings, get_settings
from app.database import get_db
from app.models.category import Category
from app.models.post import Post, PostStatus
from app.models.telegram_update import TelegramUpdate
from app.schemas.telegram import (
    TelegramDocument,
    TelegramMessage,
    TelegramUpdate as TelegramUpdatePayload,
)
from app.services.article import create_draft
from app.services.telegram import TelegramAPIError, TelegramService
from app.services.uploads import save_telegram_image


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/telegram",
    tags=["telegram"],
)


# =========================================================
# Messages
# =========================================================

WELCOME_MESSAGE = (
    "Welcome! 👋\n\n"
    "To publish a new article:\n\n"
    "1️⃣ Send a photo with a short caption.\n"
    "   The caption will become the article title.\n\n"
    "2️⃣ I will ask you for the article text.\n"
    "   Send the article text as a separate message.\n\n"
    "3️⃣ I will ask you to choose a category.\n"
    "   Reply with the category name or number.\n\n"
    "That's it — your article will be published to the website. ✅"
)

HELP_MESSAGE = (
    f"{WELCOME_MESSAGE}\n\n"
    "Available commands:\n"
    "/latest — show recent articles\n"
    "/edit — edit an article\n"
    "/delete — delete an article\n"
)

EMPTY_MESSAGE = (
    "Please send some article text, or send a photo with a caption."
)

PHOTO_CAPTION_REQUIRED = (
    "Please send the photo again with an article caption."
)

SAVE_FAILED_MESSAGE = (
    "Sorry, I couldn't save your article. Please try again."
)

NO_PENDING_MESSAGE = (
    "I don't have an article waiting for a category. "
    "Please send an article or photo with a caption first."
)

CATEGORY_INVALID_MESSAGE = (
    "I couldn't match that category. "
    "Please reply with a category name or number.\n\n"
)

IMAGE_SAVE_FAILED_MESSAGE = (
    "Sorry, I couldn't save your photo. Please try again."
)

CATEGORY_MESSAGE = (
    "Which category should this article belong to?\n\n"
    + "\n".join(
        f"{number}. {name}"
        for number, name in enumerate(CATEGORY_NAMES, start=1)
    )
    + "\n\n"
    "Reply with the category name or its number."
)

LATEST_EMPTY_MESSAGE = (
    "There are no published articles yet."
)

DELETE_USAGE_MESSAGE = (
    "To delete an article:\n\n"
    "/delete POST_ID\n\n"
    "Example:\n"
    "/delete 19\n\n"
    "I will ask you to confirm before deleting it."
)

EDIT_USAGE_MESSAGE = (
    "To edit an article:\n\n"
    "/edit POST_ID category CATEGORY\n"
    "/edit POST_ID title NEW TITLE\n"
    "/edit POST_ID text NEW ARTICLE TEXT\n\n"
    "Examples:\n"
    "/edit 19 category Mind & Mood\n"
    "/edit 19 title My new title\n"
    "/edit 19 text My new article text"
)


# =========================================================
# Telegram service
# =========================================================

def get_telegram_service(
    settings: Settings = Depends(get_settings),
) -> TelegramService:
    return TelegramService(settings)


# =========================================================
# Main webhook
# =========================================================

@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    telegram: TelegramService = Depends(get_telegram_service),
) -> dict[str, bool]:

    # -----------------------------------------------------
    # Verify Telegram webhook secret
    # -----------------------------------------------------

    provided_secret = request.headers.get(
        "X-Telegram-Bot-Api-Secret-Token",
        "",
    )

    expected_secret = (
        settings.telegram_webhook_secret.get_secret_value()
        if settings.telegram_webhook_secret is not None
        else ""
    )

    if not expected_secret or not hmac.compare_digest(
        provided_secret.encode("utf-8"),
        expected_secret.encode("utf-8"),
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid webhook credentials",
        )

    if not settings.telegram_is_configured:
        raise HTTPException(
            status_code=503,
            detail="Telegram webhook is not configured",
        )

    # -----------------------------------------------------
    # Validate Telegram payload
    # -----------------------------------------------------

    try:
        raw_payload = await request.json()

        payload = TelegramUpdatePayload.model_validate(
            raw_payload
        )

    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail="Invalid Telegram update",
        ) from exc

    message = payload.message

    if message is None:
        return {"ok": True}

    # -----------------------------------------------------
    # Check authorized Telegram user
    # -----------------------------------------------------

    sender_id = (
        message.from_user.id
        if message.from_user is not None
        else None
    )

    if sender_id != settings.telegram_allowed_user_id:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized Telegram user",
        )

    # -----------------------------------------------------
    # Logging
    # -----------------------------------------------------

    raw_message = (
        raw_payload.get("message")
        if isinstance(raw_payload, dict)
        else None
    )

    media_fields = (
        [
            field
            for field in (
                "photo",
                "document",
                "video",
                "animation",
                "sticker",
            )
            if field in raw_message
        ]
        if isinstance(raw_message, dict)
        else []
    )

    logger.info(
        "Authorized Telegram update %s media fields: %s; "
        "caption_present=%s",
        payload.update_id,
        ",".join(media_fields) or "none",
        message.caption is not None,
    )

    # -----------------------------------------------------
    # Get chat
    # -----------------------------------------------------

    chat_id = _chat_id(message, sender_id)

    if chat_id is None:
        return {"ok": True}

    # -----------------------------------------------------
    # Idempotency
    # -----------------------------------------------------

    if _update_exists(db, payload.update_id):
        return await _retry_confirmation(
            db,
            payload.update_id,
            telegram,
            chat_id,
        )

    # =====================================================
    # Commands
    # =====================================================

    command = _command(message.text)

    if command == "/start":
        return await _record_and_reply(
            db,
            payload.update_id,
            telegram,
            chat_id,
            WELCOME_MESSAGE,
        )

    if command == "/help":
        return await _record_and_reply(
            db,
            payload.update_id,
            telegram,
            chat_id,
            HELP_MESSAGE,
        )

    if command == "/latest":
        return await _handle_latest(
            db=db,
            update_id=payload.update_id,
            telegram=telegram,
            chat_id=chat_id,
        )

    if command == "/delete":
        return await _handle_delete_command(
            db=db,
            update_id=payload.update_id,
            telegram=telegram,
            chat_id=chat_id,
            text=message.text or "",
        )

    if command == "/edit":
        return await _handle_edit_command(
            db=db,
            update_id=payload.update_id,
            telegram=telegram,
            chat_id=chat_id,
            text=message.text or "",
        )

    if command is not None:
        return await _record_and_reply(
            db,
            payload.update_id,
            telegram,
            chat_id,
            HELP_MESSAGE,
        )

    # =====================================================
    # Continue an existing article
    # =====================================================

    pending_post = _get_pending_post(db)

    if pending_post is not None and not pending_post.content.strip():

        if message.text is None or not message.text.strip():
            return await _record_and_reply(
                db,
                payload.update_id,
                telegram,
                chat_id,
                EMPTY_MESSAGE,
            )

        pending_post.content = message.text.strip()

        try:
            db.commit()

        except SQLAlchemyError:
            db.rollback()

            await _send_save_failure(
                telegram,
                chat_id,
                payload.update_id,
            )

            raise HTTPException(
                status_code=503,
                detail="The article body could not be saved",
            ) from None

        try:
            await telegram.send_message(
                chat_id,
                CATEGORY_MESSAGE,
            )

        except TelegramAPIError:
            logger.warning(
                "Could not send category request after saving "
                "article body for update %s",
                payload.update_id,
            )

            raise HTTPException(
                status_code=503,
                detail=(
                    "Article body was saved, but Telegram "
                    "response could not be sent"
                ),
            ) from None

        return {"ok": True}

    # =====================================================
    # Check whether this message is a category
    # =====================================================

    category = _find_category(
        db,
        message.text,
    )

    if category is not None:
        return await _handle_category(
            db=db,
            update_id=payload.update_id,
            telegram=telegram,
            chat_id=chat_id,
            category=category,
        )

    # =====================================================
    # New article/photo submission
    # =====================================================

    content, file_id = _article_content(message)

    if content is None:
        reply = (
            PHOTO_CAPTION_REQUIRED
            if (
                message.photo
                or _is_image_document(message.document)
            )
            else EMPTY_MESSAGE
        )

        return await _record_and_reply(
            db,
            payload.update_id,
            telegram,
            chat_id,
            reply,
        )

    # -----------------------------------------------------
    # Continue existing article draft
    # -----------------------------------------------------

    pending_post = _get_pending_post(db)

    if pending_post is not None:

        if not pending_post.content.strip():

            pending_post.content = content.strip()

            try:
                db.commit()

            except SQLAlchemyError:
                db.rollback()

                await _send_save_failure(
                    telegram,
                    chat_id,
                    payload.update_id,
                )

                raise HTTPException(
                    status_code=503,
                    detail="The article body could not be saved",
                ) from None

            try:
                await telegram.send_message(
                    chat_id,
                    CATEGORY_MESSAGE,
                )

            except TelegramAPIError:
                logger.warning(
                    "Could not send category request after saving "
                    "article body for update %s",
                    payload.update_id,
                )

                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Article body was saved, but Telegram "
                        "response could not be sent"
                    ),
                ) from None

            return {"ok": True}

        reply = (
            CATEGORY_INVALID_MESSAGE
            + CATEGORY_MESSAGE
        )

        return await _record_and_reply(
            db,
            payload.update_id,
            telegram,
            chat_id,
            reply,
        )

    # =====================================================
    # Save image locally
    # =====================================================

    featured_image_url = None
    saved_image_path: Path | None = None

    if file_id is not None:

        try:
            file_info = await telegram.get_file(file_id)

            telegram_file_path = file_info.get(
                "file_path"
            )

            if not isinstance(
                telegram_file_path,
                str,
            ):
                raise TelegramAPIError(
                    "Telegram returned an invalid file response"
                )

            image_content = await telegram.download_file(
                telegram_file_path
            )

            (
                featured_image_url,
                saved_image_path,
            ) = save_telegram_image(
                image_content,
                telegram_file_path,
            )

        except TelegramAPIError:

            logger.warning(
                "Could not retrieve photo for Telegram "
                "update %s",
                payload.update_id,
            )

            await _send_image_save_failure(
                telegram,
                chat_id,
                payload.update_id,
            )

            raise HTTPException(
                status_code=503,
                detail=(
                    "The photo could not be retrieved "
                    "from Telegram"
                ),
            ) from None

        except OSError:

            logger.exception(
                "Could not store photo for Telegram update %s",
                payload.update_id,
            )

            await _send_image_save_failure(
                telegram,
                chat_id,
                payload.update_id,
            )

            raise HTTPException(
                status_code=503,
                detail="The photo could not be saved",
            ) from None

    # =====================================================
    # Record Telegram update
    # =====================================================

    try:

        telegram_update = TelegramUpdate(
            update_id=payload.update_id,
        )

        db.add(telegram_update)
        db.flush()

    except IntegrityError:

        db.rollback()

        if saved_image_path is not None:
            saved_image_path.unlink(
                missing_ok=True
            )

        if _update_exists(
            db,
            payload.update_id,
        ):
            return await _retry_confirmation(
                db,
                payload.update_id,
                telegram,
                chat_id,
            )

        logger.error(
            "Database constraint failed while recording "
            "Telegram update %s",
            payload.update_id,
        )

        await _send_save_failure(
            telegram,
            chat_id,
            payload.update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    except SQLAlchemyError as exc:

        db.rollback()

        if saved_image_path is not None:
            saved_image_path.unlink(
                missing_ok=True
            )

        logger.exception(
            "Database failed while recording Telegram "
            "update %s: %s",
            payload.update_id,
            exc,
        )

        await _send_save_failure(
            telegram,
            chat_id,
            payload.update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    # =====================================================
    # Create temporary draft
    # =====================================================

    try:

        post = create_draft(
            db,
            title=content.strip()[:255],
            content="",
            slug_seed=f"new-article-{payload.update_id}",
            telegram_file_id=file_id,
            featured_image_url=featured_image_url,
        )

        telegram_update.post_id = post.id

        db.commit()

    except SQLAlchemyError:

        db.rollback()

        if saved_image_path is not None:
            saved_image_path.unlink(
                missing_ok=True
            )

        logger.exception(
            "Database failed while saving draft for "
            "Telegram update %s",
            payload.update_id,
        )

        await _send_save_failure(
            telegram,
            chat_id,
            payload.update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    # =====================================================
    # Ask Mom for article text
    # =====================================================

    try:

        await telegram.send_message(
            chat_id,
            "Great! 👍\n\nNow send me the article text.",
        )

    except TelegramAPIError:

        logger.warning(
            "Could not send article text request "
            "for update %s",
            payload.update_id,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Article was saved, but Telegram "
                "response could not be sent"
            ),
        ) from None

    return {"ok": True}


# =========================================================
# /latest
# =========================================================

async def _handle_latest(
    *,
    db: Session,
    update_id: int,
    telegram: TelegramService,
    chat_id: int,
) -> dict[str, bool]:

    posts = db.scalars(
        select(Post)
        .where(
            Post.status == PostStatus.PUBLISHED
        )
        .order_by(
            Post.published_at.desc(),
            Post.id.desc(),
        )
        .limit(10)
    ).all()

    if not posts:
        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            LATEST_EMPTY_MESSAGE,
        )

    lines = [
        "Recent published articles:\n"
    ]

    for post in posts:

        category = (
            db.get(
                Category,
                post.category_id,
            )
            if post.category_id is not None
            else None
        )

        category_name = (
            category.name
            if category is not None
            else "Uncategorized"
        )

        lines.append(
            f"#{post.id} — {post.title}\n"
            f"Category: {category_name}\n"
        )

    reply = "\n".join(lines)

    return await _record_and_reply(
        db,
        update_id,
        telegram,
        chat_id,
        reply,
    )


# =========================================================
# /delete
# =========================================================

async def _handle_delete_command(
    *,
    db: Session,
    update_id: int,
    telegram: TelegramService,
    chat_id: int,
    text: str,
) -> dict[str, bool]:

    parts = text.strip().split(
        maxsplit=2
    )

    if (
        len(parts) < 2
        or not parts[1].isdigit()
    ):
        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            DELETE_USAGE_MESSAGE,
        )

    post_id = int(parts[1])

    post = db.get(
        Post,
        post_id,
    )

    if (
        post is None
        or post.status != PostStatus.PUBLISHED
    ):
        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            (
                f"I couldn't find published "
                f"article #{post_id}."
            ),
        )

    # -----------------------------------------------------
    # First command: ask for confirmation
    # -----------------------------------------------------

    if len(parts) == 2:

        reply = (
            "⚠️ Please confirm deletion.\n\n"
            f"#{post.id} — {post.title}\n\n"
            "This will remove the article from the "
            "website.\n\n"
            f"To confirm, send:\n"
            f"/delete {post.id} confirm"
        )

        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            reply,
        )

    # -----------------------------------------------------
    # Confirmation
    # -----------------------------------------------------

    if parts[2].casefold() != "confirm":

        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            (
                "Deletion was not confirmed.\n\n"
                f"To confirm, send:\n"
                f"/delete {post.id} confirm"
            ),
        )

    # -----------------------------------------------------
    # Delete local image after archiving article
    # -----------------------------------------------------

    image_path: Path | None = None

    if post.featured_image_url:

        image_name = Path(
            post.featured_image_url
        ).name

        image_path = (
            Path(__file__).resolve().parents[2]
            / "uploads"
            / image_name
        )

    try:

        # We archive instead of physically deleting
        # the database row. This protects TelegramUpdate
        # foreign-key relationships and keeps history safe.

        post.status = PostStatus.ARCHIVED

        db.commit()

    except SQLAlchemyError:

        db.rollback()

        logger.exception(
            "Failed to delete/archive post %s",
            post_id,
        )

        await _send_save_failure(
            telegram,
            chat_id,
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The article could not be deleted",
        ) from None

    # Remove local image if one exists.
    if image_path is not None:

        try:
            image_path.unlink(
                missing_ok=True
            )

        except OSError:

            logger.warning(
                "Could not remove image for archived "
                "post %s: %s",
                post_id,
                image_path,
            )

    return await _record_and_reply(
        db,
        update_id,
        telegram,
        chat_id,
        (
            "Deleted successfully. 🗑️\n\n"
            f"Article #{post.id} is no longer visible "
            "on the website."
        ),
    )


# =========================================================
# /edit
# =========================================================

async def _handle_edit_command(
    *,
    db: Session,
    update_id: int,
    telegram: TelegramService,
    chat_id: int,
    text: str,
) -> dict[str, bool]:

    parts = text.strip().split(
        maxsplit=3
    )

    if len(parts) < 4 or not parts[1].isdigit():

        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            EDIT_USAGE_MESSAGE,
        )

    post_id = int(parts[1])
    field = parts[2].casefold()
    value = parts[3].strip()

    post = db.get(
        Post,
        post_id,
    )

    if (
        post is None
        or post.status != PostStatus.PUBLISHED
    ):
        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            (
                f"I couldn't find published "
                f"article #{post_id}."
            ),
        )

    if not value:

        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            EDIT_USAGE_MESSAGE,
        )

    # -----------------------------------------------------
    # Edit category
    # -----------------------------------------------------

    if field == "category":

        category = _find_category(
            db,
            value,
        )

        if category is None:

            return await _record_and_reply(
                db,
                update_id,
                telegram,
                chat_id,
                (
                    CATEGORY_INVALID_MESSAGE
                    + CATEGORY_MESSAGE
                ),
            )

        post.category_id = category.id

    # -----------------------------------------------------
    # Edit title
    # -----------------------------------------------------

    elif field == "title":

        post.title = value[:255]

    # -----------------------------------------------------
    # Edit article text
    # -----------------------------------------------------

    elif field == "text":

        post.content = value

    else:

        return await _record_and_reply(
            db,
            update_id,
            telegram,
            chat_id,
            EDIT_USAGE_MESSAGE,
        )

    # -----------------------------------------------------
    # Save edit
    # -----------------------------------------------------

    try:

        db.commit()

    except SQLAlchemyError:

        db.rollback()

        logger.exception(
            "Failed to edit post %s",
            post_id,
        )

        await _send_save_failure(
            telegram,
            chat_id,
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The article could not be edited",
        ) from None

    # -----------------------------------------------------
    # Confirmation
    # -----------------------------------------------------

    if field == "category":

        confirmation = (
            "Updated successfully! ✅\n\n"
            f"Article: {post.title}\n"
            f"Category: {category.name}"
        )

    elif field == "title":

        confirmation = (
            "Updated successfully! ✅\n\n"
            f"New title: {post.title}"
        )

    else:

        confirmation = (
            "Updated successfully! ✅\n\n"
            f"Article #{post.id} text has been updated."
        )

    return await _record_and_reply(
        db,
        update_id,
        telegram,
        chat_id,
        confirmation,
    )


# =========================================================
# Category handling
# =========================================================

async def _handle_category(
    *,
    db: Session,
    update_id: int,
    telegram: TelegramService,
    chat_id: int,
    category: Category,
) -> dict[str, bool]:

    # -----------------------------------------------------
    # Record category-response Telegram update first
    # -----------------------------------------------------

    try:

        telegram_update = TelegramUpdate(
            update_id=update_id,
        )

        db.add(telegram_update)
        db.flush()

    except IntegrityError:

        db.rollback()

        if _update_exists(
            db,
            update_id,
        ):
            return await _retry_confirmation(
                db,
                update_id,
                telegram,
                chat_id,
            )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    except SQLAlchemyError:

        db.rollback()

        await _send_save_failure(
            telegram,
            chat_id,
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    # -----------------------------------------------------
    # Find article waiting for category
    # -----------------------------------------------------

    post = _get_pending_post(db)

    if post is None:

        try:
            db.commit()

        except SQLAlchemyError:

            db.rollback()

            await _send_save_failure(
                telegram,
                chat_id,
                update_id,
            )

            raise HTTPException(
                status_code=503,
                detail="The update could not be processed",
            ) from None

        try:

            await telegram.send_message(
                chat_id,
                NO_PENDING_MESSAGE,
            )

        except TelegramAPIError:

            logger.warning(
                "Could not send no-pending response "
                "for update %s",
                update_id,
            )

        return {"ok": True}

    # -----------------------------------------------------
    # Publish immediately
    # -----------------------------------------------------

    try:

        post.category_id = category.id

        post.status = PostStatus.PUBLISHED

        post.published_at = (
            datetime.now(UTC)
            .replace(tzinfo=None)
        )

        telegram_update.post_id = post.id

        db.commit()

    except SQLAlchemyError:

        db.rollback()

        logger.exception(
            "Database failed while publishing post %s",
            post.id,
        )

        await _send_save_failure(
            telegram,
            chat_id,
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The article could not be published",
        ) from None

    # -----------------------------------------------------
    # Confirmation
    # -----------------------------------------------------

    try:

        await _send_published_confirmation(
            telegram,
            chat_id,
            post,
            category,
        )

    except TelegramAPIError:

        logger.warning(
            "Could not send published confirmation "
            "for update %s",
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Article was published, but Telegram "
                "confirmation could not be sent"
            ),
        ) from None

    return {"ok": True}


# =========================================================
# Generic Telegram reply
# =========================================================

async def _record_and_reply(
    db: Session,
    update_id: int,
    telegram: TelegramService,
    chat_id: int,
    reply: str,
) -> dict[str, bool]:

    try:

        db.add(
            TelegramUpdate(
                update_id=update_id,
            )
        )

        db.commit()

    except IntegrityError:

        db.rollback()

        if _update_exists(
            db,
            update_id,
        ):
            return {"ok": True}

        await _send_save_failure(
            telegram,
            chat_id,
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    except SQLAlchemyError:

        db.rollback()

        await _send_save_failure(
            telegram,
            chat_id,
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail="The update could not be processed",
        ) from None

    try:

        await telegram.send_message(
            chat_id,
            reply,
        )

    except TelegramAPIError:

        logger.warning(
            "Could not send Telegram response "
            "for update %s",
            update_id,
        )

    return {"ok": True}


# =========================================================
# Error messages
# =========================================================

async def _send_save_failure(
    telegram: TelegramService,
    chat_id: int,
    update_id: int,
) -> None:

    try:

        await telegram.send_message(
            chat_id,
            SAVE_FAILED_MESSAGE,
        )

    except TelegramAPIError:

        logger.warning(
            "Could not send Telegram error response "
            "for update %s",
            update_id,
        )


async def _send_image_save_failure(
    telegram: TelegramService,
    chat_id: int,
    update_id: int,
) -> None:

    try:

        await telegram.send_message(
            chat_id,
            IMAGE_SAVE_FAILED_MESSAGE,
        )

    except TelegramAPIError:

        logger.warning(
            "Could not send Telegram photo error response "
            "for update %s",
            update_id,
        )


# =========================================================
# Idempotency
# =========================================================

def _update_exists(
    db: Session,
    update_id: int,
) -> bool:

    return (
        db.scalar(
            select(TelegramUpdate.id).where(
                TelegramUpdate.update_id == update_id
            )
        )
        is not None
    )


async def _retry_confirmation(
    db: Session,
    update_id: int,
    telegram: TelegramService,
    chat_id: int,
) -> dict[str, bool]:

    post_id = db.scalar(
        select(TelegramUpdate.post_id).where(
            TelegramUpdate.update_id == update_id
        )
    )

    if post_id is None:
        return {"ok": True}

    post = db.get(
        Post,
        post_id,
    )

    if post is None:
        return {"ok": True}

    try:

        if post.status == PostStatus.PUBLISHED:

            category = (
                db.get(
                    Category,
                    post.category_id,
                )
                if post.category_id is not None
                else None
            )

            if category is not None:

                await _send_published_confirmation(
                    telegram,
                    chat_id,
                    post,
                    category,
                )

        else:

            await telegram.send_message(
                chat_id,
                CATEGORY_MESSAGE,
            )

    except TelegramAPIError:

        logger.warning(
            "Could not retry Telegram confirmation "
            "for update %s",
            update_id,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Telegram confirmation could not be sent"
            ),
        ) from None

    return {"ok": True}


# =========================================================
# Publish confirmation
# =========================================================

async def _send_published_confirmation(
    telegram: TelegramService,
    chat_id: int,
    post: Post,
    category: Category,
) -> None:

    confirmation = (
        "Published successfully! ✅\n\n"
        f"Title: {post.title}\n"
        f"Category: {category.name}\n"
        f"Post ID: {post.id}\n"
        "Status: published"
    )

    await telegram.send_message(
        chat_id,
        confirmation,
    )


# =========================================================
# Pending article
# =========================================================

def _get_pending_post(
    db: Session,
) -> Post | None:

    return db.scalar(
        select(Post)
        .join(
            TelegramUpdate,
            TelegramUpdate.post_id == Post.id,
        )
        .where(
            Post.status == PostStatus.DRAFT,
            TelegramUpdate.post_id.is_not(None),
        )
        .order_by(
            TelegramUpdate.id.desc()
        )
        .limit(1)
    )


# =========================================================
# Category lookup
# =========================================================

def _find_category(
    db: Session,
    text: str | None,
) -> Category | None:

    if text is None or not text.strip():
        return None

    value = text.strip()

    categories = {
        category.name.casefold(): category
        for category in db.scalars(
            select(Category)
        )
    }

    # Number selection
    if value.isdigit():

        number = int(value)

        if 1 <= number <= len(CATEGORY_NAMES):

            return categories.get(
                CATEGORY_NAMES[number - 1].casefold()
            )

        return None

    # Name selection
    return categories.get(
        value.casefold()
    )


# =========================================================
# Chat ID
# =========================================================

def _chat_id(
    message: TelegramMessage,
    sender_id: int,
) -> int | None:

    chat = message.chat

    if chat is None:
        return sender_id

    return chat.id


# =========================================================
# Command parser
# =========================================================

def _command(
    text: str | None,
) -> str | None:

    if not text or not text.startswith("/"):
        return None

    first_word = text.split(
        maxsplit=1
    )[0]

    command, separator, _bot_name = (
        first_word.partition("@")
    )

    return (
        command
        if separator or command.startswith("/")
        else None
    )


# =========================================================
# Article content
# =========================================================

def _article_content(
    message: TelegramMessage,
) -> tuple[str | None, str | None]:

    file_id = (
        message.photo[-1].file_id
        if message.photo
        else (
            message.document.file_id
            if (
                _is_image_document(
                    message.document
                )
                and message.document is not None
            )
            else None
        )
    )

    # -----------------------------------------------------
    # Photo/document with caption
    # -----------------------------------------------------

    if file_id is not None:

        if (
            message.caption is None
            or not message.caption.strip()
        ):
            return None, None

        return (
            message.caption,
            file_id,
        )

    # -----------------------------------------------------
    # Text message
    # -----------------------------------------------------

    if (
        message.text is None
        or not message.text.strip()
    ):
        return None, None

    return (
        message.text,
        None,
    )


# =========================================================
# Image document detection
# =========================================================

def _is_image_document(
    document: TelegramDocument | None,
) -> bool:

    if document is None:
        return False

    image_extensions = {
        ".avif",
        ".bmp",
        ".gif",
        ".jpeg",
        ".jpg",
        ".png",
        ".tif",
        ".tiff",
        ".webp",
    }

    mime_type = (
        document.mime_type or ""
    ).casefold()

    extension = Path(
        document.file_name or ""
    ).suffix.casefold()

    return (
        mime_type.startswith("image/")
        and mime_type != "image/svg+xml"
    ) or extension in image_extensions