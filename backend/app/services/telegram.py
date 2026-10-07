from typing import Any
from urllib.parse import quote

import httpx

from app.config import Settings

MAX_TELEGRAM_FILE_BYTES = 20 * 1024 * 1024


class TelegramAPIError(Exception):
    """A Telegram API failure with no token or response details attached."""


class TelegramService:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = (
            settings.telegram_bot_token.get_secret_value()
            if settings.telegram_bot_token is not None
            else None
        )
        self._transport = transport

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._request("sendMessage", {"chat_id": chat_id, "text": text})

    async def get_file(self, file_id: str) -> dict[str, Any]:
        response = await self._request("getFile", {"file_id": file_id})
        result = response.get("result")
        if not isinstance(result, dict):
            raise TelegramAPIError("Telegram returned an invalid file response")
        return result

    async def download_file(self, file_path: str) -> bytes:
        if self._token is None:
            raise TelegramAPIError("Telegram bot is not configured")
        if (
            not file_path
            or file_path.startswith("/")
            or "\\" in file_path
            or any(part in {"", ".", ".."} for part in file_path.split("/"))
        ):
            raise TelegramAPIError("Telegram returned an invalid file path")

        url = (
            f"https://api.telegram.org/file/bot{self._token}/"
            f"{quote(file_path, safe='/')}"
        )

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                transport=self._transport,
            ) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length is not None and int(content_length) > MAX_TELEGRAM_FILE_BYTES:
                        raise TelegramAPIError("Telegram image exceeds the download limit")

                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_TELEGRAM_FILE_BYTES:
                            raise TelegramAPIError("Telegram image exceeds the download limit")
        except TelegramAPIError:
            raise
        except (httpx.HTTPError, ValueError):
            raise TelegramAPIError("Telegram file download failed") from None

        if not content:
            raise TelegramAPIError("Telegram returned an empty image")
        return bytes(content)

    async def set_webhook(self, url: str, secret_token: str) -> None:
        await self._request(
            "setWebhook",
            {
                "url": url,
                "secret_token": secret_token,
                "allowed_updates": ["message"],
            },
        )

    async def _request(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if self._token is None:
            raise TelegramAPIError("Telegram bot is not configured")

        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self._token}/{method}",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError):
            raise TelegramAPIError("Telegram API request failed") from None

        if not isinstance(data, dict) or data.get("ok") is not True:
            raise TelegramAPIError("Telegram API request failed")
        return data
