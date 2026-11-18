"""Central posting orchestrator service executing multi-platform publication."""

import asyncio
import re
from typing import List, Optional, Sequence

from app.config import settings
from app.platforms.base import BasePlatform
from app.platforms.telegram import TelegramPlatform
from app.platforms.discord import DiscordPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.mastodon import MastodonPlatform
from app.schemas import PlatformResult, PostingResponse


class PostingService:
    """
    Central orchestrator service that coordinates asynchronous publication
    across all supported social media platforms.
    """

    REQUIRED_PLATFORMS = ("Telegram", "Discord", "Reddit", "LinkedIn", "Mastodon")

    def __init__(self, platforms: Optional[Sequence[BasePlatform]] = None) -> None:
        """
        Initialize the posting service with target platforms.

        Args:
            platforms: Optional sequence of platform adapters. If omitted, initializes
                       the standard five platform adapters in deterministic order.
                       If provided, must contain exactly the 5 required platforms
                       without duplicates, omissions, or unexpected platforms.
        """
        if platforms is not None:
            self._validate_platforms(platforms)
            self.platforms: List[BasePlatform] = list(platforms)
        else:
            self.platforms = [
                TelegramPlatform(),
                DiscordPlatform(),
                RedditPlatform(),
                LinkedInPlatform(),
                MastodonPlatform(),
            ]

    @classmethod
    def _validate_platforms(cls, platforms: Sequence[BasePlatform]) -> None:
        """
        Validate that the platform configuration contains exactly the five
        required platforms without duplicates, omissions, or unexpected platforms.
        """
        if not isinstance(platforms, (list, tuple)):
            raise ValueError("PostingService platforms must be a list or tuple of BasePlatform instances.")

        if not platforms:
            raise ValueError(
                "PostingService platforms list cannot be empty. "
                f"Exactly 5 platforms are required: {', '.join(cls.REQUIRED_PLATFORMS)}."
            )

        seen = set()
        for p in platforms:
            if not isinstance(p, BasePlatform):
                raise ValueError(f"Invalid platform adapter: {p} must inherit from BasePlatform.")

            name = p.platform_name
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"Platform adapter {p} has an invalid or empty platform_name.")

            if name not in cls.REQUIRED_PLATFORMS:
                raise ValueError(
                    f"Unexpected platform '{name}'. Expected one of: {', '.join(cls.REQUIRED_PLATFORMS)}."
                )

            if name in seen:
                raise ValueError(f"Duplicate platform detected in PostingService configuration: '{name}'.")
            seen.add(name)

        missing = set(cls.REQUIRED_PLATFORMS) - seen
        if missing:
            raise ValueError(
                f"PostingService configuration is missing required platforms: {', '.join(sorted(missing))}."
            )

    @classmethod
    def _sanitize_error_text(cls, message: str, platform: Optional[BasePlatform] = None) -> str:
        """
        Ensure unexpected errors never leak sensitive credentials, tokens, or webhook secrets.
        """
        if not message:
            return ""

        sanitized = message

        # 1. Platform-specific sanitizer if provided on adapter
        if platform and hasattr(platform, "_sanitize_error") and callable(platform._sanitize_error):
            try:
                sanitized = platform._sanitize_error(sanitized)
            except Exception:
                pass

        # 2. Inspect adapter instance attributes
        if platform:
            for attr in (
                "bot_token",
                "webhook_url",
                "client_secret",
                "refresh_token",
                "access_token",
            ):
                val = getattr(platform, attr, None)
                if val and isinstance(val, str) and val.strip() and val in sanitized:
                    sanitized = sanitized.replace(val, "[REDACTED_CREDENTIAL]")

        # 3. Global settings credential scrub
        known_secrets = (
            settings.TELEGRAM_BOT_TOKEN,
            settings.DISCORD_WEBHOOK_URL,
            settings.REDDIT_CLIENT_SECRET,
            settings.REDDIT_REFRESH_TOKEN,
            settings.REDDIT_ACCESS_TOKEN,
            settings.LINKEDIN_ACCESS_TOKEN,
            settings.MASTODON_ACCESS_TOKEN,
        )
        for sec in known_secrets:
            if sec and isinstance(sec, str) and sec.strip() and sec in sanitized:
                sanitized = sanitized.replace(sec, "[REDACTED_CREDENTIAL]")

        # 4. Regex scrub for Discord webhook URLs and tokens
        sanitized = re.sub(
            r"https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+",
            "https://discord.com/api/webhooks/[REDACTED_DISCORD_WEBHOOK]",
            sanitized,
        )

        # 5. Regex scrub for Telegram bot tokens in URLs or logs (bot<digits>:<token>)
        sanitized = re.sub(
            r"bot\d+:[A-Za-z0-9_-]+",
            "bot[REDACTED_BOT_TOKEN]",
            sanitized,
        )

        # 6. Regex scrub for Bearer auth tokens
        sanitized = re.sub(
            r"Bearer\s+[A-Za-z0-9._~+/-]+",
            "Bearer [REDACTED_TOKEN]",
            sanitized,
            flags=re.IGNORECASE,
        )

        return sanitized

    async def _safe_publish(
        self, platform: BasePlatform, message: str, url: str
    ) -> PlatformResult:
        """
        Safely invoke publish on a platform adapter, catching any unhandled exceptions,
        sanitizing credentials, and validating the returned PlatformResult to guarantee
        complete failure isolation and result integrity.
        """
        try:
            result = await platform.publish(message, url)

            # 1. Type validation
            if not isinstance(result, PlatformResult):
                return PlatformResult(
                    platform=platform.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=f"{platform.platform_name} adapter returned an invalid result object.",
                )

            # 2. Platform name consistency validation
            if result.platform != platform.platform_name:
                return PlatformResult(
                    platform=platform.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=(
                        f"{platform.platform_name} adapter returned mismatched platform name "
                        f"'{result.platform}'."
                    ),
                )

            # 3. Status value validation
            if result.status not in ("success", "failed"):
                return PlatformResult(
                    platform=platform.platform_name,
                    status="failed",
                    posted_url=None,
                    public_access=False,
                    date=None,
                    time=None,
                    error=f"{platform.platform_name} adapter returned an invalid status '{result.status}'.",
                )

            return result

        except Exception as exc:
            raw_err = f"{platform.platform_name} unexpected error: {type(exc).__name__} - {exc}"
            sanitized_err = self._sanitize_error_text(raw_err, platform=platform)
            return PlatformResult(
                platform=platform.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=sanitized_err,
            )

    async def post_to_all(self, message: str, url: str) -> PostingResponse:
        """
        Publish the validated message and CTA link across all configured platforms concurrently.

        Args:
            message: The full validated promotional text (<= 200 chars).
            url: The extracted single validated CTA URL.

        Returns:
            PostingResponse: Aggregated response containing overall success status
                             and individual PlatformResult entries for each platform.
        """
        tasks = [self._safe_publish(platform, message, url) for platform in self.platforms]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results: List[PlatformResult] = []
        for i, res in enumerate(raw_results):
            if isinstance(res, PlatformResult):
                final_results.append(res)
            elif isinstance(res, Exception):
                p_name = self.platforms[i].platform_name if i < len(self.platforms) else "Unknown"
                platform_inst = self.platforms[i] if i < len(self.platforms) else None
                raw_err = f"{p_name} execution error: {type(res).__name__} - {res}"
                sanitized_err = self._sanitize_error_text(raw_err, platform=platform_inst)
                final_results.append(
                    PlatformResult(
                        platform=p_name,
                        status="failed",
                        posted_url=None,
                        public_access=False,
                        date=None,
                        time=None,
                        error=sanitized_err,
                    )
                )

        overall_success = (
            len(final_results) == len(self.REQUIRED_PLATFORMS)
            and all(r.status == "success" for r in final_results)
        )
        return PostingResponse(success=overall_success, results=final_results)

    async def publish(self, message: str, url: str) -> PostingResponse:
        """Convenience alias for post_to_all."""
        return await self.post_to_all(message, url)
