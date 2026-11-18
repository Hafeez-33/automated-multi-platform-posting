"""LinkedIn platform adapter implementation using the official REST Posts API."""

import datetime
from typing import Optional
import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


class LinkedInPlatform(BasePlatform):
    """Platform adapter for publishing posts to LinkedIn via the REST Posts API."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        author_urn: Optional[str] = None,
        linkedin_version: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.access_token = access_token if access_token is not None else settings.LINKEDIN_ACCESS_TOKEN
        self.author_urn = author_urn if author_urn is not None else settings.LINKEDIN_AUTHOR_URN
        self.linkedin_version = linkedin_version if linkedin_version is not None else settings.LINKEDIN_VERSION
        self.timeout = timeout if timeout is not None else 10.0

    @property
    def platform_name(self) -> str:
        """Human-readable platform name."""
        return "LinkedIn"

    def _sanitize_error(self, message: str) -> str:
        """Ensure the LinkedIn access token is never exposed in error messages."""
        if not message:
            return ""
        sanitized = message
        if self.access_token and self.access_token.strip() and self.access_token.strip() in sanitized:
            sanitized = sanitized.replace(self.access_token.strip(), "[REDACTED_ACCESS_TOKEN]")
        return sanitized

    async def publish(self, message: str, url: str) -> PlatformResult:
        """
        Publish a promotional message containing a CTA link to LinkedIn.

        Args:
            message: The full validated text message to post.
            url: The extracted single validated CTA URL.

        Returns:
            PlatformResult: Result containing status, post URL, timestamps, or error.
        """
        # 1. Missing credentials or author check
        if (
            not self.access_token
            or not self.access_token.strip()
            or not self.author_urn
            or not self.author_urn.strip()
        ):
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=(
                    "LinkedIn configuration error: Missing required credentials. "
                    "Provide LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN."
                ),
            )

        api_url = "https://api.linkedin.com/rest/posts"
        version = self.linkedin_version.strip() if self.linkedin_version else "202611"

        headers = {
            "Authorization": f"Bearer {self.access_token.strip()}",
            "LinkedIn-Version": version,
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

        payload = {
            "author": self.author_urn.strip(),
            "commentary": message,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(api_url, json=payload, headers=headers)

            response.raise_for_status()

            # Post identifier is returned in the x-restli-id response header
            post_id = response.headers.get("x-restli-id") or response.headers.get("X-RestLi-Id")

            # Fallback to response JSON if header is absent
            response_json = {}
            if response.content:
                try:
                    data = response.json()
                    if isinstance(data, dict):
                        response_json = data
                        if not post_id:
                            post_id = data.get("id")
                except Exception as json_err:
                    if not post_id:
                        return PlatformResult(
                            platform=self.platform_name,
                            status="failed",
                            posted_url=None,
                            public_access=False,
                            date=None,
                            time=None,
                            error=self._sanitize_error(
                                f"LinkedIn unexpected response: Failed to parse JSON ({json_err})."
                            ),
                        )

            if not post_id or not str(post_id).strip():
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error="LinkedIn response did not contain a valid post identifier in headers or body.",
                )

            # Publication timestamp: parse if returned by LinkedIn, otherwise None
            pub_date: Optional[datetime.date] = None
            pub_time: Optional[datetime.time] = None

            raw_timestamp = (
                response_json.get("createdAt")
                or response_json.get("created")
                or response_json.get("timestamp")
            )
            if raw_timestamp:
                try:
                    if isinstance(raw_timestamp, (int, float)):
                        ts = raw_timestamp / 1000.0 if raw_timestamp > 1e11 else float(raw_timestamp)
                        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                    else:
                        dt = datetime.datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
                    pub_date = dt.date()
                    pub_time = dt.time()
                except (ValueError, TypeError, OverflowError):
                    pub_date = None
                    pub_time = None

            # Conservative reporting: LinkedIn REST API provides URNs, not canonical public URLs.
            # Feed posts are also access-gated for unauthenticated visitors.
            return PlatformResult(
                platform=self.platform_name,
                status="success",
                posted_url=None,
                public_access=False,
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
                error="LinkedIn request timed out.",
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            try:
                err_data = exc.response.json()
                error_desc = err_data.get("message") or err_data.get("errorDetailType") or exc.response.text
            except Exception:
                error_desc = exc.response.text or f"HTTP {status_code}"

            if status_code == 401:
                prefix = "LinkedIn authentication failed: HTTP 401 -"
            elif status_code == 403:
                prefix = "LinkedIn permission denied: HTTP 403 -"
            elif status_code == 400:
                prefix = "LinkedIn validation error: HTTP 400 -"
            else:
                prefix = f"LinkedIn HTTP {status_code} error:"

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
                error=self._sanitize_error(f"LinkedIn network error: {type(exc).__name__} - {exc}"),
            )
        except Exception as exc:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"LinkedIn unexpected error: {type(exc).__name__} - {exc}"),
            )
