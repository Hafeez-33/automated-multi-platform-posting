"""Mastodon platform adapter implementation using the official REST Statuses API."""

import datetime
from typing import Optional
import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


def normalize_instance_url(url: Optional[str]) -> str:
    """
    Normalize the Mastodon instance URL to ensure a proper HTTP/HTTPS scheme
    and strip trailing slashes, preventing duplicate slashes in the final endpoint.
    """
    if not url or not url.strip():
        return "https://mastodon.social"
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned.rstrip("/")


class MastodonPlatform(BasePlatform):
    """Platform adapter for publishing statuses to Mastodon via the REST API."""

    def __init__(
        self,
        instance_url: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.instance_url = instance_url if instance_url is not None else settings.MASTODON_INSTANCE_URL
        self.access_token = access_token if access_token is not None else settings.MASTODON_ACCESS_TOKEN
        self.timeout = timeout if timeout is not None else 10.0

    @property
    def platform_name(self) -> str:
        """Human-readable platform name."""
        return "Mastodon"

    def _sanitize_error(self, message: str) -> str:
        """Ensure the Mastodon access token is never exposed in error messages."""
        if not message:
            return ""
        sanitized = message
        if self.access_token and self.access_token.strip() and self.access_token.strip() in sanitized:
            sanitized = sanitized.replace(self.access_token.strip(), "[REDACTED_ACCESS_TOKEN]")
        return sanitized

    async def publish(self, message: str, url: str) -> PlatformResult:
        """
        Publish a promotional message containing a CTA link to Mastodon.

        Args:
            message: The full validated text message to post.
            url: The extracted single validated CTA URL.

        Returns:
            PlatformResult: Result containing status, post URL, timestamps, or error.
        """
        # 1. Missing credentials check
        if not self.access_token or not self.access_token.strip():
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=(
                    "Mastodon configuration error: Missing required credentials. "
                    "Provide MASTODON_ACCESS_TOKEN."
                ),
            )

        base_url = normalize_instance_url(self.instance_url)
        endpoint = f"{base_url}/api/v1/statuses"

        headers = {
            "Authorization": f"Bearer {self.access_token.strip()}",
            "Content-Type": "application/json",
        }

        payload = {
            "status": message,
            "visibility": "public",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(endpoint, json=payload, headers=headers)

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
                    error=self._sanitize_error(
                        f"Mastodon unexpected response: Failed to parse JSON ({json_err})."
                    ),
                )

            if not isinstance(data, dict):
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=self._sanitize_error(
                        "Mastodon unexpected response: Response body was not a JSON object."
                    ),
                )

            if "error" in data:
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=self._sanitize_error(f"Mastodon API error: {data['error']}"),
                )

            posted_url = data.get("url")
            if not posted_url or not isinstance(posted_url, str) or not posted_url.strip():
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=self._sanitize_error(
                        "Mastodon response did not provide a valid status URL."
                    ),
                )

            # Public access evaluation: True only if the returned visibility is public
            raw_visibility = data.get("visibility")
            public_access = bool(
                isinstance(raw_visibility, str) and raw_visibility.strip().lower() == "public"
            )

            # Publication timestamp: parse created_at ISO 8601 string if present
            pub_date: Optional[datetime.date] = None
            pub_time: Optional[datetime.time] = None

            raw_created_at = data.get("created_at")
            if raw_created_at:
                try:
                    dt = datetime.datetime.fromisoformat(str(raw_created_at).replace("Z", "+00:00"))
                    pub_date = dt.date()
                    pub_time = dt.time()
                except (ValueError, TypeError):
                    pub_date = None
                    pub_time = None

            return PlatformResult(
                platform=self.platform_name,
                status="success",
                posted_url=posted_url.strip(),
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
                error="Mastodon request timed out.",
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_data = exc.response.json()
                error_desc = err_data.get("error_description") or err_data.get("error") or exc.response.text
            except Exception:
                error_desc = exc.response.text or f"HTTP {status_code}"

            if status_code == 401:
                prefix = "Mastodon authentication failed: HTTP 401 -"
            elif status_code == 403:
                prefix = "Mastodon permission denied: HTTP 403 -"
            elif status_code == 422:
                prefix = "Mastodon validation error: HTTP 422 -"
            else:
                prefix = f"Mastodon HTTP {status_code} error:"

            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"{prefix} {error_desc}"),
            )
        except httpx.RequestError as exc:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"Mastodon network error: {type(exc).__name__} - {exc}"),
            )
        except Exception as exc:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"Mastodon unexpected error: {type(exc).__name__} - {exc}"),
            )
