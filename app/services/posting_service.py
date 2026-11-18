"""Central posting orchestrator service executing multi-platform publication."""

import asyncio
from typing import List, Optional

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

    def __init__(self, platforms: Optional[List[BasePlatform]] = None) -> None:
        """
        Initialize the posting service with target platforms.

        Args:
            platforms: Optional list of platform adapters. If omitted, initializes
                       the standard five platform adapters in deterministic order.
        """
        if platforms is not None:
            self.platforms = platforms
        else:
            self.platforms = [
                TelegramPlatform(),
                DiscordPlatform(),
                RedditPlatform(),
                LinkedInPlatform(),
                MastodonPlatform(),
            ]

    async def _safe_publish(
        self, platform: BasePlatform, message: str, url: str
    ) -> PlatformResult:
        """
        Safely invoke publish on a platform adapter, catching any unhandled exceptions
        and converting them to a failed PlatformResult to guarantee complete failure isolation.
        """
        try:
            result = await platform.publish(message, url)
            if isinstance(result, PlatformResult):
                return result
            return PlatformResult(
                platform=platform.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=f"{platform.platform_name} adapter returned an invalid result.",
            )
        except Exception as exc:
            err_msg = f"{platform.platform_name} unexpected error: {type(exc).__name__} - {exc}"
            if hasattr(platform, "_sanitize_error") and callable(platform._sanitize_error):
                err_msg = platform._sanitize_error(err_msg)
            return PlatformResult(
                platform=platform.platform_name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error=err_msg,
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
                final_results.append(
                    PlatformResult(
                        platform=p_name,
                        status="failed",
                        posted_url=None,
                        public_access=False,
                        date=None,
                        time=None,
                        error=f"{p_name} execution error: {type(res).__name__} - {res}",
                    )
                )

        overall_success = bool(final_results) and all(r.status == "success" for r in final_results)
        return PostingResponse(success=overall_success, results=final_results)

    async def publish(self, message: str, url: str) -> PostingResponse:
        """Convenience alias for post_to_all."""
        return await self.post_to_all(message, url)
