"""Reddit platform adapter implementation using the official OAuth 2.0 Data API."""

import datetime
from typing import Optional
import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


class RedditPlatform(BasePlatform):
    """Platform adapter for publishing text posts to Reddit via OAuth 2.0."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        access_token: Optional[str] = None,
        user_agent: Optional[str] = None,
        subreddit: Optional[str] = None,
        timeout: float = 10.0,
    ) -> None:
        self.client_id = client_id if client_id is not None else settings.REDDIT_CLIENT_ID
        self.client_secret = client_secret if client_secret is not None else settings.REDDIT_CLIENT_SECRET
        self.refresh_token = refresh_token if refresh_token is not None else settings.REDDIT_REFRESH_TOKEN
        self.access_token = access_token if access_token is not None else settings.REDDIT_ACCESS_TOKEN
        self.user_agent = user_agent if user_agent is not None else settings.REDDIT_USER_AGENT
        self.subreddit = subreddit if subreddit is not None else settings.REDDIT_SUBREDDIT
        self.timeout = timeout

    @property
    def platform_name(self) -> str:
        """Human-readable platform name."""
        return "Reddit"

    def _sanitize_error(self, message: str) -> str:
        """Ensure client secrets, refresh tokens, and access tokens are never exposed in error text."""
        sanitized = message
        for secret in (self.client_secret, self.refresh_token, self.access_token):
            if secret and secret in sanitized:
                sanitized = sanitized.replace(secret, "[REDACTED_CREDENTIAL]")
        return sanitized

    async def _obtain_access_token(self, client: httpx.AsyncClient) -> str:
        """
        Obtain a valid access token using the refresh token flow if a direct token is not provided.
        Raises an exception on failure.
        """
        if self.access_token and self.access_token.strip():
            return self.access_token.strip()

        token_url = "https://www.reddit.com/api/v1/access_token"
        auth = (self.client_id or "", self.client_secret or "")
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token or "",
        }
        headers = {
            "User-Agent": self.user_agent or "AutomatedPoster/1.0.0",
        }

        resp = await client.post(token_url, auth=auth, data=data, headers=headers)
        resp.raise_for_status()

        token_data = resp.json()
        if not isinstance(token_data, dict):
            raise ValueError("Reddit token response was not a valid JSON object.")

        if "error" in token_data:
            raise ValueError(f"Reddit token error: {token_data.get('error')}")

        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError("Reddit token response did not contain 'access_token'.")

        return str(access_token)

    async def publish(self, message: str, url: str) -> PlatformResult:
        """
        Publish a message containing a CTA link to Reddit as a self/text post.

        Args:
            message: The full validated text message to post.
            url: The extracted single validated CTA URL.

        Returns:
            PlatformResult: Result containing status, post URL, timestamps, or error.
        """
        # 1. Missing credentials check
        has_direct_token = bool(self.access_token and self.access_token.strip())
        has_refresh_flow = bool(
            self.client_id
            and self.client_id.strip()
            and self.client_secret
            and self.client_secret.strip()
            and self.refresh_token
            and self.refresh_token.strip()
        )

        if not has_direct_token and not has_refresh_flow:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=(
                    "Reddit configuration error: Missing required credentials. "
                    "Provide REDDIT_ACCESS_TOKEN or REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, "
                    "and REDDIT_REFRESH_TOKEN."
                ),
            )

        target_sr = (self.subreddit or "test").lstrip("r/").strip()
        if not target_sr:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error="Reddit configuration error: Missing or empty REDDIT_SUBREDDIT.",
            )

        # Derive a concise post title from the message (Reddit requires a title)
        first_line = message.split("\n")[0].strip()
        title = first_line[:80].strip() if first_line else "Announcement"

        submit_url = "https://oauth.reddit.com/api/submit"
        payload = {
            "api_type": "json",
            "sr": target_sr,
            "kind": "self",
            "title": title,
            "text": message,
            "resubmit": "true",
            "send_replies": "true",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # 2. Obtain access token
                try:
                    token = await self._obtain_access_token(client)
                except httpx.HTTPStatusError as auth_http_err:
                    err_msg = auth_http_err.response.text or f"HTTP {auth_http_err.response.status_code}"
                    return PlatformResult(
                        platform=self.platform_name,
                        status="failed",
                        posted_url=None,
                        public_access=False,
                        date=None,
                        time=None,
                        error=self._sanitize_error(
                            f"Reddit authentication failed: HTTP {auth_http_err.response.status_code} - {err_msg}"
                        ),
                    )
                except Exception as auth_err:
                    return PlatformResult(
                        platform=self.platform_name,
                        status="failed",
                        posted_url=None,
                        public_access=False,
                        date=None,
                        time=None,
                        error=self._sanitize_error(f"Reddit authentication failed: {auth_err}"),
                    )

                # 3. Submit post to Reddit
                headers = {
                    "Authorization": f"Bearer {token}",
                    "User-Agent": self.user_agent or "AutomatedPoster/1.0.0",
                }
                response = await client.post(submit_url, data=payload, headers=headers)

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
                    error=f"Reddit unexpected response: Failed to parse JSON ({json_err}).",
                )

            if not isinstance(data, dict) or "json" not in data:
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error="Reddit unexpected response: Missing 'json' root object.",
                )

            json_body = data["json"]
            errors = json_body.get("errors", [])
            if errors:
                err_details = ", ".join(
                    f"{err[0]}: {err[1]}" if isinstance(err, (list, tuple)) and len(err) >= 2 else str(err)
                    for err in errors
                )
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=self._sanitize_error(f"Reddit API rejection: {err_details}"),
                )

            post_data = json_body.get("data", {})
            posted_url = post_data.get("url")
            if not posted_url or not isinstance(posted_url, str):
                return PlatformResult(
                    platform=self.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error="Reddit response did not provide a published post URL.",
                )

            # Publication timestamp: parse if returned by Reddit, otherwise None
            pub_date: Optional[datetime.date] = None
            pub_time: Optional[datetime.time] = None
            raw_timestamp = post_data.get("created_utc") or post_data.get("timestamp")
            if raw_timestamp:
                try:
                    if isinstance(raw_timestamp, (int, float)):
                        dt = datetime.datetime.fromtimestamp(raw_timestamp, tz=datetime.timezone.utc)
                    else:
                        dt = datetime.datetime.fromisoformat(str(raw_timestamp))
                    pub_date = dt.date()
                    pub_time = dt.time()
                except (ValueError, TypeError):
                    pub_date = None
                    pub_time = None

            # Public access evaluation: public subreddit posts are accessible to the public
            public_access = True

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
                error="Reddit request timed out.",
            )
        except httpx.HTTPStatusError as exc:
            try:
                err_data = exc.response.json()
                error_desc = err_data.get("message", exc.response.text)
            except Exception:
                error_desc = exc.response.text or f"HTTP {exc.response.status_code}"
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"Reddit HTTP {exc.response.status_code} error: {error_desc}"),
            )
        except httpx.RequestError as exc:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"Reddit network error: {type(exc).__name__} - {exc}"),
            )
        except Exception as exc:
            return PlatformResult(
                platform=self.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=self._sanitize_error(f"Reddit unexpected error: {type(exc).__name__} - {exc}"),
            )
