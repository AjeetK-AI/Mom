import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.categories import CATEGORY_NAME_SLUGS, CATEGORY_NAMES
from app.database import get_db
from app.main import app
from app.models.category import Category
from app.models.post import Post, PostStatus
from app.models.telegram_update import TelegramUpdate
from app.services.telegram import TelegramAPIError, TelegramService
from app.services.uploads import UPLOAD_DIRECTORY

pytestmark = pytest.mark.asyncio
WEBHOOK = "/api/telegram/webhook"
SECRET_HEADER = {"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"}
def update(update_id: int, *, user_id: int = 42, message: dict | None = None) -> dict:
    if message is None:
        message = {"text": "Education is very important for every child."}
    return {
        "update_id": update_id,
        "message": {
            "from": {"id": user_id, "is_bot": False, "first_name": "Mom"},
            "chat": {"id": user_id, "type": "private"},
            **message,
        },
    }


def seed_categories(factory: sessionmaker[Session]) -> None:
    with factory() as db:
        db.add_all(
            [
                Category(name=name, slug=slug)
                for name, slug in CATEGORY_NAME_SLUGS
            ]
        )
        db.commit()


async def test_valid_webhook_saves_exact_text_as_uncategorized_draft(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    source = "  Education is very important for every child.\nAll children deserve to learn.  "
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1001, message={"text": source}),
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    _, factory = test_app
    with factory() as db:
        post = db.scalar(select(Post))
        assert post is not None
        assert post.content == source
        assert post.title == "New Article"
        assert post.summary is None
        assert post.category_id is None
        assert post.status == PostStatus.DRAFT
        assert db.scalar(select(TelegramUpdate.update_id)) == 1001

    prompt = json.loads(api_stub.calls[0].content)["text"]
    assert prompt.startswith("Which category should this article belong to?")
    for number, category in enumerate(CATEGORY_NAMES, start=1):
        assert f"{number}. {category}" in prompt
    with factory() as db:
        update_record = db.scalar(select(TelegramUpdate))
        assert update_record is not None
        assert update_record.post_id == post.id


async def test_invalid_secret_is_rejected_without_writes(
    client: httpx.AsyncClient,
    test_app: tuple,
) -> None:
    response = await client.post(
        WEBHOOK,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        json=update(1002),
    )
    assert response.status_code == 403
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 0


async def test_invalid_update_payload_is_rejected(
    client: httpx.AsyncClient,
    test_app: tuple,
) -> None:
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json={"update_id": "not-an-integer", "message": {}},
    )
    assert response.status_code == 422
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 0


async def test_unauthorized_user_is_rejected_without_writes(
    client: httpx.AsyncClient,
    test_app: tuple,
) -> None:
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1003, user_id=999),
    )
    assert response.status_code == 403
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 0


async def test_duplicate_update_retries_confirmation_without_duplicate_draft(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    payload = update(1004)
    first = await client.post(WEBHOOK, headers=SECRET_HEADER, json=payload)
    second = await client.post(WEBHOOK, headers=SECRET_HEADER, json=payload)
    assert first.status_code == second.status_code == 200
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 1
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 1
    assert len(api_stub.calls) == 2
    assert json.loads(api_stub.calls[0].content)["text"] == json.loads(
        api_stub.calls[1].content
    )["text"]


async def test_empty_message_requests_article_text(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1005, message={"text": "  "}),
    )
    assert response.status_code == 200
    assert json.loads(api_stub.calls[0].content)["text"] == (
        "Please send some article text, or send a photo with a caption."
    )
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 1


async def test_start_command(client: httpx.AsyncClient, api_stub) -> None:
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1006, message={"text": "/start"}),
    )
    assert response.status_code == 200
    assert json.loads(api_stub.calls[0].content)["text"] == (
        "Welcome! Send me an article or a photo with a caption. "
        "I will ask you for the category and publish it."
    )


async def test_help_command(client: httpx.AsyncClient, api_stub) -> None:
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1007, message={"text": "/help"}),
    )
    assert response.status_code == 200
    reply = json.loads(api_stub.calls[0].content)["text"]
    assert "photo with a caption" in reply.lower()
    assert "ask you for the category and publish it" in reply.lower()
    assert "category name or its number" in reply.lower()


async def test_photo_caption_saves_file_id_for_later_processing(
    client: httpx.AsyncClient,
    test_app: tuple,
) -> None:
    image_path: Path | None = None
    try:
        _, factory = test_app
        seed_categories(factory)
        response = await client.post(
            WEBHOOK,
            headers=SECRET_HEADER,
            json=update(
                1008,
                message={
                    "caption": "  A caption that becomes the article.  ",
                    "photo": [{"file_id": "small"}, {"file_id": "largest-photo-file-id"}],
                },
            ),
        )
        assert response.status_code == 200
        with factory() as db:
            post = db.scalar(select(Post))
            assert post is not None
            assert post.content == "  A caption that becomes the article.  "
            assert post.telegram_file_id == "largest-photo-file-id"
            assert post.featured_image_url is not None
            assert post.featured_image_url.startswith("/uploads/")
            image_path = UPLOAD_DIRECTORY / post.featured_image_url.rsplit("/", 1)[1]

        assert image_path.read_bytes() == b"telegram image bytes"
        draft_list = await client.get("/api/posts")
        assert draft_list.status_code == 200
        assert draft_list.json()["items"] == []

        publish = await client.post(
            WEBHOOK,
            headers=SECRET_HEADER,
            json=update(1031, message={"text": "Food & Juices"}),
        )
        assert publish.status_code == 200
        public_posts = await client.get("/api/posts")
        public_post = public_posts.json()["items"][0]
        assert public_post["category"]["name"] == "Food & Juices"
        assert public_post["content"] == "  A caption that becomes the article.  "
        assert public_post["featured_image_url"].startswith("/uploads/")
        assert public_post["published_at"] is not None

        served = await client.get(post.featured_image_url)
        assert served.status_code == 200
        assert served.content == b"telegram image bytes"
    finally:
        if image_path is not None:
            image_path.unlink(missing_ok=True)


async def test_photo_without_caption_requests_caption(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1009, message={"photo": [{"file_id": "photo-file-id"}]}),
    )
    assert response.status_code == 200
    assert json.loads(api_stub.calls[0].content)["text"] == (
        "Please send the photo again with an article caption."
    )
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0


async def test_image_document_with_caption_downloads_and_publishes_image(
    client: httpx.AsyncClient,
    test_app: tuple,
) -> None:
    image_path: Path | None = None
    try:
        _, factory = test_app
        seed_categories(factory)
        submission = await client.post(
            WEBHOOK,
            headers=SECRET_HEADER,
            json=update(
                1033,
                message={
                    "caption": "Second database test 999",
                    "document": {
                        "file_id": "telegram-document-image-id",
                        "file_name": "family-picture.jpg",
                        "mime_type": "image/jpeg",
                    },
                },
            ),
        )
        assert submission.status_code == 200
        with factory() as db:
            post = db.scalar(select(Post))
            assert post is not None
            assert post.status == PostStatus.DRAFT
            assert post.content == "Second database test 999"
            assert post.telegram_file_id == "telegram-document-image-id"
            assert post.featured_image_url is not None
            image_path = UPLOAD_DIRECTORY / post.featured_image_url.rsplit("/", 1)[1]
            post_id = post.id

        assert image_path.read_bytes() == b"telegram image bytes"
        published = await client.post(
            WEBHOOK,
            headers=SECRET_HEADER,
            json=update(1034, message={"text": "Stories & Reflections"}),
        )
        assert published.status_code == 200

        with factory() as db:
            post = db.get(Post, post_id)
            assert post is not None
            assert post.status == PostStatus.PUBLISHED
            assert post.category is not None
            assert post.category.name == "Stories & Reflections"
            image_url = post.featured_image_url
            assert image_url is not None

        served_image = await client.get(image_url)
        assert served_image.status_code == 200
        assert served_image.content == b"telegram image bytes"
    finally:
        if image_path is not None:
            image_path.unlink(missing_ok=True)


async def test_category_name_publishes_the_pending_post(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    _, factory = test_app
    seed_categories(factory)

    submitted = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1020, message={"text": "A memory from our family."}),
    )
    published = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1021, message={"text": "mInD & mOoD"}),
    )
    assert submitted.status_code == published.status_code == 200
    confirmation = json.loads(api_stub.calls[-1].content)["text"]
    assert "Published successfully!" in confirmation
    assert "Category: Mind & Mood" in confirmation
    assert "Status: published" in confirmation

    with factory() as db:
        post = db.scalar(select(Post))
        assert post is not None
        assert post.content == "A memory from our family."
        assert post.category is not None
        assert post.category.name == "Mind & Mood"
        assert post.status == PostStatus.PUBLISHED
        assert post.published_at is not None
        assert db.scalar(select(func.count(Post.id))) == 1
        category_update = db.scalar(
            select(TelegramUpdate).where(TelegramUpdate.update_id == 1021)
        )
        assert category_update is not None
        assert category_update.post_id == post.id


async def test_numeric_category_uses_the_listed_order(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    _, factory = test_app
    seed_categories(factory)
    await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1022, message={"text": "Another family memory."}),
    )
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1023, message={"text": "7"}),
    )

    assert response.status_code == 200
    assert "Category: Stories & Reflections" in json.loads(api_stub.calls[-1].content)["text"]
    with factory() as db:
        post = db.scalar(select(Post))
        assert post is not None
        assert post.category is not None
        assert post.category.name == "Stories & Reflections"
        assert post.status == PostStatus.PUBLISHED


async def test_invalid_category_does_not_publish_or_create_another_post(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    _, factory = test_app
    seed_categories(factory)
    await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1024, message={"text": "An article waiting for a category."}),
    )
    invalid = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1025, message={"text": "Not a category"}),
    )
    assert invalid.status_code == 200
    assert json.loads(api_stub.calls[-1].content)["text"].startswith(
        "I couldn't match that category."
    )

    second_article = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1026, message={"text": "A second article"}),
    )
    assert second_article.status_code == 200
    assert "category" in json.loads(api_stub.calls[-1].content)["text"].lower()
    with factory() as db:
        posts = list(db.scalars(select(Post)))
        assert len(posts) == 1
        assert posts[0].status == PostStatus.DRAFT
        assert posts[0].category_id is None


async def test_duplicate_category_update_does_not_publish_a_second_post(
    client: httpx.AsyncClient,
    test_app: tuple,
) -> None:
    _, factory = test_app
    seed_categories(factory)
    await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1027, message={"text": "One published article."}),
    )
    category_reply = update(1028, message={"text": "Food & Juices"})
    first = await client.post(WEBHOOK, headers=SECRET_HEADER, json=category_reply)
    duplicate = await client.post(WEBHOOK, headers=SECRET_HEADER, json=category_reply)
    assert first.status_code == duplicate.status_code == 200

    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 1
        post = db.scalar(select(Post))
        assert post is not None
        assert post.status == PostStatus.PUBLISHED
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 2


async def test_database_failure_while_publishing_rolls_back_category_update(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    _, factory = test_app
    seed_categories(factory)
    await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1029, message={"text": "Publish only after category."}),
    )

    def failing_db() -> Iterator[Session]:
        with factory() as db:
            def fail_commit() -> None:
                raise OperationalError("COMMIT", {}, RuntimeError("database unavailable"))

            db.commit = fail_commit  # type: ignore[method-assign]
            yield db

    app.dependency_overrides[get_db] = failing_db
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(1030, message={"text": "Nutrition Notes"}),
    )
    assert response.status_code == 503
    assert json.loads(api_stub.calls[-1].content)["text"] == (
        "Sorry, I couldn't save your article. Please try again."
    )
    with factory() as db:
        post = db.scalar(select(Post))
        assert post is not None
        assert post.status == PostStatus.DRAFT
        assert post.category_id is None
        assert db.scalar(
            select(func.count(TelegramUpdate.id)).where(
                TelegramUpdate.update_id == 1030
            )
        ) == 0


async def test_telegram_api_failure_retries_confirmation_without_duplicate_draft(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    api_stub.status_code = 500
    response = await client.post(WEBHOOK, headers=SECRET_HEADER, json=update(1010))
    assert response.status_code == 503
    api_stub.status_code = 200
    retry = await client.post(WEBHOOK, headers=SECRET_HEADER, json=update(1010))
    assert retry.status_code == 200
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 1
        update_record = db.scalar(select(TelegramUpdate))
        assert update_record is not None
        assert update_record.post_id is not None


async def test_database_failure_rolls_back_update_and_draft_and_replies_friendly(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
) -> None:
    _, factory = test_app

    def failing_db() -> Iterator[Session]:
        with factory() as db:
            def fail_commit() -> None:
                raise OperationalError("COMMIT", {}, RuntimeError("database unavailable"))

            db.commit = fail_commit  # type: ignore[method-assign]
            yield db

    from app.database import get_db

    app.dependency_overrides[get_db] = failing_db
    response = await client.post(WEBHOOK, headers=SECRET_HEADER, json=update(1011))
    assert response.status_code == 503
    assert json.loads(api_stub.calls[0].content)["text"] == (
        "Sorry, I couldn't save your article. Please try again."
    )
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 0


async def test_telegram_file_failure_does_not_create_a_post_or_log_the_token(
    client: httpx.AsyncClient,
    test_app: tuple,
    api_stub,
    settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    api_stub.status_code = 500
    response = await client.post(
        WEBHOOK,
        headers=SECRET_HEADER,
        json=update(
            1032,
            message={
                "caption": "A photo whose download will fail.",
                "photo": [{"file_id": "photo-file-id"}],
            },
        ),
    )
    assert response.status_code == 503
    assert settings.telegram_bot_token.get_secret_value() not in caplog.text
    _, factory = test_app
    with factory() as db:
        assert db.scalar(select(func.count(Post.id))) == 0
        assert db.scalar(select(func.count(TelegramUpdate.id))) == 0


async def test_telegram_service_hides_bot_token_on_api_error(settings) -> None:
    async def fail(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"ok": False, "description": "failure"})

    service = TelegramService(settings, transport=httpx.MockTransport(fail))
    with pytest.raises(TelegramAPIError) as error:
        await service.send_message(42, "test")
    assert settings.telegram_bot_token.get_secret_value() not in str(error.value)


async def test_telegram_service_wraps_get_file_and_set_webhook(settings) -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, content=b"image bytes")
        result = (
            {"file_path": "photos/example.jpg"}
            if request.url.path.endswith("/getFile")
            else True
        )
        return httpx.Response(200, json={"ok": True, "result": result})

    file_service = TelegramService(settings, transport=httpx.MockTransport(respond))
    file_result = await file_service.get_file("telegram-file-id")
    assert file_result == {"file_path": "photos/example.jpg"}
    assert await file_service.download_file("photos/example.jpg") == b"image bytes"

    webhook_service = TelegramService(settings, transport=httpx.MockTransport(respond))
    await webhook_service.set_webhook(
        "https://example-tunnel.test/api/telegram/webhook",
        "a-random-webhook-secret",
    )

    assert requests[0].url.path.endswith("/getFile")
    assert json.loads(requests[0].content) == {"file_id": "telegram-file-id"}
    assert requests[1].url.path.endswith("/photos/example.jpg")
    assert requests[2].url.path.endswith("/setWebhook")
    webhook_payload = json.loads(requests[2].content)
    assert webhook_payload["secret_token"] == "a-random-webhook-secret"
    assert webhook_payload["url"] == "https://example-tunnel.test/api/telegram/webhook"
