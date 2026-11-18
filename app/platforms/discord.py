"""Discord platform adapter implementation using the Discord Webhook API."""

import datetime
from typing import Optional
import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


class DiscordPlatform(BasePlatform):
    """Platform adapter for publishing messages to Discord channels via Webhook API."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.webhook_url = webhook_url or settings.DISCORD_WEBHOOK_URL
        self.timeout = timeout

    @property
    def platform_name(self) -> str:
        """Human-readable platform name."""
        return "Discord"

    def _sanitize_error(self, message: str) -> str:
        """Ensure webhook URL and secret token are never exposed in error messages."""
        if not self.webhook_url:
            return message

        sanitized = message.replace(self.webhook_url, "[REDACTED_DISCORD_WEBHOOK_URL]")
        # Extract and redact token if URL follows standard Discord webhook structure
        parts = self.webhook_url.rstrip("/").split("/")
        if len(parts) >= 2:
            token = parts[-1].split("?")[0]
            if len(token) > 5 and token in sanitized:
                sanitized = sanitized.replace(token, "[REDACTED_DISCORD_TOKEN]")
        return sanitized

    async def publish(self, message: str, url: str) -> PlatformResult:
        """
        Publish a message containing a CTA link to Discord via Webhook.

        Args:
            message: The full validated text message to post.
            url: The extracted single validated CTA URL.

        Returns:
            PlatformResult: Result containing status, post URL, timestamps, or error.
        """
        # 1. Missing credentials check
        if not self.webhook_url or not self.webhook_url.strip():
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error="Discord configuration error: Missing DISCORD_WEBHOOK_URL.",
            )

        # 2. Prepare endpoint with wait=true to receive the Message object
        target_url = self.webhook_url
        if "wait=" not in target_url:
            delimiter = "&" if "?" in target_url else "?"
            target_url = f"{target_url}{delimiter}wait=true"

        payload = {
            "content": message,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(target_url, json=payload)

            # Check HTTP status errors
            response.raise_for_status()

            try:
                data = response.json()
            except Exception as json_err:
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=f"Discord unexpected response: Failed to parse JSON ({json_err}).",
                )

            if not isinstance(data, dict):
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error="Discord unexpected response: Expected JSON object.",
                )

            message_id = data.get("id")
            channel_id = data.get("channel_id")
            if not message_id or not channel_id:
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error="Discord unexpected response: Missing 'id' or 'channel_id' in response.",
                )

            # Publication timestamp
            raw_timestamp = data.get("timestamp")
            dt: Optional[datetime.datetime] = None
            if raw_timestamp and isinstance(raw_timestamp, str):
                try:
                    dt = datetime.datetime.fromisoformat(raw_timestamp)
                except ValueError:
                    dt = datetime.datetime.now(datetime.timezone.utc)
            else:
                dt = datetime.datetime.now(datetime.timezone.utc)

            pub_date = dt.date()
            pub_time = dt.time()

            # Construct message URL if IDs are available
            guild_id = data.get("guild_id")
            if guild_id:
                posted_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            else:
                posted_url = f"https://discord.com/channels/@me/{channel_id}/{message_id}"

            # Discord channels require authentication and guild permissions to view
            public_access = False

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
                error="Discord request timed out.",
            )
        except httpx.HTTPStatusError as exc:
            try:
                err_data = exc.response.json()
                error_desc = err_data.get("message", exc.response.text)
            except Exception:
                error_desc = exc.response.text or f"HTTP {exc.response.status_code}"
            sanitized_msg = self._sanitize_error(
                f"Discord HTTP {exc.response.status_code} error: {error_desc}"
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
                f"Discord network error: {type(exc).__name__} - {exc}"
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
                f"Discord unexpected error: {type(exc).__name__} - {exc}"
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
