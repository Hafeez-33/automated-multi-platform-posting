"""Discord platform adapter implementation using the Discord Webhook API."""

import datetime
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


def _ensure_wait_true(url: str) -> str:
    """
    Ensure the webhook URL contains wait=true query parameter using standard URL parsing.
    Replaces existing wait=false if present, preserving all other query parameters.
    """
    parsed = urlparse(url)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_params["wait"] = "true"
    new_query = urlencode(query_params)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))


class DiscordPlatform(BasePlatform):
    """Platform adapter for publishing messages to Discord channels via Webhook API."""

    def __init__(
        self,
        webhook_url: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.webhook_url = webhook_url if webhook_url is not None else settings.DISCORD_WEBHOOK_URL
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
        target_url = _ensure_wait_true(self.webhook_url)

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

            # Publication timestamp: parse when valid, otherwise None
            pub_date: Optional[datetime.date] = None
            pub_time: Optional[datetime.time] = None
            raw_timestamp = data.get("timestamp")
            if raw_timestamp and isinstance(raw_timestamp, str):
                try:
                    dt = datetime.datetime.fromisoformat(raw_timestamp)
                    pub_date = dt.date()
                    pub_time = dt.time()
                except (ValueError, TypeError):
                    pub_date = None
                    pub_time = None

            # Construct message URL only when guild_id, channel_id, and message_id are available
            guild_id = data.get("guild_id")
            if guild_id:
                posted_url = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            else:
                posted_url = None

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
