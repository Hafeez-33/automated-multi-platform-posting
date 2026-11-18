"""Telegram platform adapter implementation using the Telegram Bot API."""

import datetime
from typing import Optional
import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


class TelegramPlatform(BasePlatform):
    """Platform adapter for publishing messages to Telegram channels via Bot API."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or settings.TELEGRAM_CHAT_ID
        self.timeout = timeout

    @property
    def platform_name(self) -> str:
        """Human-readable platform name."""
        return "Telegram"

    def _sanitize_error(self, message: str) -> str:
        """Ensure the bot token is never exposed in error messages."""
        if self.bot_token and self.bot_token in message:
            return message.replace(self.bot_token, "[REDACTED_BOT_TOKEN]")
        return message

    async def publish(self, message: str, url: str) -> PlatformResult:
        """
        Publish a message containing a CTA link to Telegram.

        Args:
            message: The full validated text message to post.
            url: The extracted single validated CTA URL.

        Returns:
            PlatformResult: Result containing status, post URL (if public), timestamps, or error.
        """
        # 1. Missing credentials check
        if not self.bot_token or not self.chat_id:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error="Telegram configuration error: Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.",
            )

        api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(api_url, json=payload)

            # Check HTTP status errors
            response.raise_for_status()

            data = response.json()

            # Confirm Telegram response indicates success
            if not isinstance(data, dict) or not data.get("ok"):
                error_desc = data.get("description", "Unknown rejection from Telegram API.")
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=self._sanitize_error(f"Telegram API error: {error_desc}"),
                )

            result_obj = data.get("result", {})
            message_id = result_obj.get("message_id")
            if message_id is None:
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error="Telegram unexpected response: missing 'message_id' in result.",
                )

            # Publication timestamp
            raw_timestamp = result_obj.get("date")
            if isinstance(raw_timestamp, (int, float)):
                dt = datetime.datetime.fromtimestamp(raw_timestamp, tz=datetime.timezone.utc)
            else:
                dt = datetime.datetime.now(datetime.timezone.utc)

            pub_date = dt.date()
            pub_time = dt.time()

            # Evaluate public access and construct posted URL
            chat_obj = result_obj.get("chat", {})
            chat_username = chat_obj.get("username")

            # A destination is demonstrably public if chat has a public username
            # or if the destination chat_id was configured with an @handle
            public_username: Optional[str] = None
            if chat_username:
                public_username = chat_username
            elif isinstance(self.chat_id, str) and self.chat_id.startswith("@"):
                public_username = self.chat_id.lstrip("@")

            if public_username:
                public_access = True
                posted_url = f"https://t.me/{public_username}/{message_id}"
            else:
                public_access = False
                posted_url = None

            return PlatformResult(
                platform=self.platform_name,
                status="success",
                posted_url=posted_url,
                public_access=public_access,
                date=pub_date,
                time=pub_time,
                error=None,
            )

        except httpx.TimeoutException:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error="Telegram request timed out.",
            )
        except httpx.HTTPStatusError as exc:
            try:
                err_data = exc.response.json()
                error_desc = err_data.get("description", exc.response.text)
            except Exception:
                error_desc = exc.response.text or f"HTTP {exc.response.status_code}"
            sanitized_msg = self._sanitize_error(
                f"Telegram HTTP {exc.response.status_code} error: {error_desc}"
            )
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=sanitized_msg,
            )
        except httpx.RequestError as exc:
            sanitized_msg = self._sanitize_error(
                f"Telegram network error: {type(exc).__name__} - {exc}"
            )
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=sanitized_msg,
            )
        except Exception as exc:
            sanitized_msg = self._sanitize_error(
                f"Telegram unexpected error: {type(exc).__name__} - {exc}"
            )
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=sanitized_msg,
            )
