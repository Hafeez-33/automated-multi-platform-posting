"""Application configuration module using Pydantic Settings."""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration settings loaded from environment or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Server settings
    APP_NAME: str = "Automated Multi-Platform Posting System"
    APP_ENV: str = "development"
    HOST: str = "0.0.0.0"
    PORT: int = 4000

    # 1. Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # 2. Discord
    DISCORD_WEBHOOK_URL: Optional[str] = None

    # 3. Reddit
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USERNAME: Optional[str] = None
    REDDIT_PASSWORD: Optional[str] = None
    REDDIT_USER_AGENT: str = "AutomatedPoster/1.0.0"
    REDDIT_SUBREDDIT: str = "test"

    # 4. LinkedIn
    LINKEDIN_ACCESS_TOKEN: Optional[str] = None
    LINKEDIN_AUTHOR_URN: Optional[str] = None

    # 5. Mastodon
    MASTODON_INSTANCE_URL: str = "https://mastodon.social"
    MASTODON_ACCESS_TOKEN: Optional[str] = None


settings = Settings()
