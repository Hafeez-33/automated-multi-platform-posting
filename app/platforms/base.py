"""Abstract base class defining the uniform contract for all platform adapters."""

from abc import ABC, abstractmethod
from app.schemas import PlatformResult


class BasePlatform(ABC):
    """
    Abstract base class for all third-party publishing platforms.

    Enforces a consistent asynchronous publishing contract across all integrations
    (Telegram, Discord, Reddit, LinkedIn, Mastodon).
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable name of the platform (e.g. 'Telegram', 'Discord')."""
        ...

    @abstractmethod
    async def publish(self, message: str, url: str) -> PlatformResult:
        """
        Publish a message containing a CTA link to the third-party platform.

        Args:
            message: The full validated promotional text (<= 200 characters).
            url: The extracted single validated CTA URL.

        Returns:
            PlatformResult: Structured result containing platform name, status
                            ('success' or 'failed'), posted URL, public access flag,
                            date, time, and error details (if any).
        """
        ...
