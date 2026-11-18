"""Tests for Pydantic schemas, input validation rules, and endpoint schema verification."""

import datetime
from typing import Optional
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas import PlatformResult, PostingRequest, PostingResponse


client = TestClient(app)


# ==============================================================================
# Unit Tests: Pydantic PostingRequest Validation
# ==============================================================================

def test_valid_message_with_one_url():
    """Verify that a valid message with exactly one HTTP/HTTPS URL passes validation."""
    valid_text = (
        "Check out our latest business platform and grow your online visibility. https://example.com"
    )
    req = PostingRequest(message=valid_text)
    assert req.message == valid_text
    assert req.extracted_url == "https://example.com"


def test_valid_message_with_punctuation_around_url():
    """Verify that trailing punctuation (e.g. sentence-ending period) is handled correctly."""
    valid_text = "Visit our portal today: https://example.com/welcome."
    req = PostingRequest(message=valid_text)
    assert req.extracted_url == "https://example.com/welcome"


def test_empty_message():
    """Verify that an empty or whitespace-only message is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="")
    assert "Message must not be empty" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="   ")
    assert "Message must not be empty" in str(exc_info.value)


def test_message_exceeding_200_characters():
    """Verify that a message longer than 200 characters is rejected."""
    long_prefix = "A" * 185
    long_message = f"{long_prefix} https://example.com"  # 185 + 1 + 19 = 205 chars
    assert len(long_message) > 200

    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message=long_message)
    assert "200 characters" in str(exc_info.value)


def test_missing_url():
    """Verify that a message containing zero URLs is rejected."""
    text_without_link = "Check out our latest business platform and grow your online visibility."
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message=text_without_link)
    assert "Message must contain exactly one valid CTA URL" in str(exc_info.value)


def test_multiple_urls():
    """Verify that a message containing more than one URL is rejected."""
    multi_url_text = "Check https://first.com and also see https://second.com for more info."
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message=multi_url_text)
    assert "Message contains 2 URLs. Exactly one CTA URL is allowed" in str(exc_info.value)


def test_invalid_url_syntax():
    """Verify that malformed or incomplete URLs are rejected."""
    # Empty host after scheme
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="Check out https:// for details.")
    assert "missing a valid domain/host name" in str(exc_info.value)

    # Invalid host ending with dot
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="Check out https://example..com for details.")
    assert "invalid host name" in str(exc_info.value)

    # Missing TLD (not localhost)
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="Check out https://nonexistentdomain without tld.")
    assert "must contain a top-level domain" in str(exc_info.value)


def test_unsupported_url_scheme():
    """Verify that non-HTTP/HTTPS schemes and raw www. links are rejected."""
    # FTP scheme
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="Download file at ftp://files.example.com/package.zip")
    assert "scheme 'ftp' is not supported" in str(exc_info.value)

    # Raw www. without scheme
    with pytest.raises(ValidationError) as exc_info:
        PostingRequest(message="Visit www.example.com for our services.")
    assert "must include an HTTP or HTTPS scheme" in str(exc_info.value)


# ==============================================================================
# Unit Tests: Response Models Serialization
# ==============================================================================

def test_response_model_serialization():
    """Verify correct schema structure and serialization of PlatformResult and PostingResponse."""
    success_result = PlatformResult(
        platform="Telegram",
        status="success",
        posted_url="https://t.me/example_channel/42",
        public_access=True,
        date=datetime.date(2026, 11, 15),
        time=datetime.time(10, 30, 0),
        error=None,
    )

    failed_result = PlatformResult(
        platform="Discord",
        status="failed",
        posted_url=None,
        public_access=False,
        date=None,
        time=None,
        error="Authentication failed: 401 Unauthorized",
    )

    response = PostingResponse(
        success=True,
        results=[success_result, failed_result],
    )

    dumped = response.model_dump(mode="json")

    # Assert top-level structure
    assert dumped["success"] is True
    assert len(dumped["results"]) == 2

    # Assert success platform fields
    assert dumped["results"][0] == {
        "platform": "Telegram",
        "status": "success",
        "posted_url": "https://t.me/example_channel/42",
        "public_access": True,
        "date": "2026-11-15",
        "time": "10:30:00",
        "error": None,
    }

    # Assert failed platform fields
    assert dumped["results"][1] == {
        "platform": "Discord",
        "status": "failed",
        "posted_url": None,
        "public_access": False,
        "date": None,
        "time": None,
        "error": "Authentication failed: 401 Unauthorized",
    }


# ==============================================================================
# Endpoint Integration Tests: POST /posting
# ==============================================================================

def test_endpoint_valid_request():
    """Verify that POST /posting accepts a valid payload and returns 200 with schema structure."""
    payload = {
        "message": "Check out our latest business platform and grow your online visibility. https://example.com"
    }
    response = client.post("/posting", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "success" in data
    assert "results" in data
    assert isinstance(data["results"], list)


@pytest.mark.parametrize(
    "invalid_payload,expected_error_substr",
    [
        ({"message": ""}, "Message must not be empty"),
        ({"message": "A" * 201 + " https://example.com"}, "200 characters"),
        ({"message": "No link in this message."}, "Message must contain exactly one valid CTA URL"),
        ({"message": "Two links https://a.com and https://b.com"}, "Exactly one CTA URL is allowed"),
        ({"message": "Unsupported ftp://example.com/file"}, "scheme 'ftp' is not supported"),
        ({"message": "Malformed link https://"}, "missing a valid domain/host name"),
    ],
)
def test_endpoint_validation_errors(invalid_payload, expected_error_substr):
    """Verify that POST /posting returns HTTP 422 with meaningful validation error messages."""
    response = client.post("/posting", json=invalid_payload)
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    error_str = str(data["detail"])
    assert expected_error_substr in error_str


# ==============================================================================
# Unit Tests: BasePlatform Interface Contract
# ==============================================================================

def test_base_platform_cannot_be_instantiated_directly():
    """Verify that BasePlatform is an abstract class and cannot be instantiated directly."""
    from app.platforms.base import BasePlatform

    with pytest.raises(TypeError) as exc_info:
        BasePlatform()  # type: ignore
    assert "Can't instantiate abstract class BasePlatform" in str(exc_info.value)


@pytest.mark.asyncio
async def test_concrete_platform_subclass_can_be_instantiated_and_executed():
    """Verify that a concrete subclass implementing platform_name and publish() can be instantiated."""
    from app.platforms.base import BasePlatform
    from app.schemas import PlatformResult

    class MockPlatform(BasePlatform):
        platform_name = "MockPlatform"

        async def publish(self, message: str, url: str) -> PlatformResult:
            return PlatformResult(
                platform=self.platform_name,
                status="success",
                posted_url=f"https://mock.platform.com/post?url={url}",
                public_access=True,
                error=None,
            )

    platform = MockPlatform()
    assert platform.platform_name == "MockPlatform"

    result = await platform.publish("Test message https://example.com", "https://example.com")
    assert isinstance(result, PlatformResult)
    assert result.platform == "MockPlatform"
    assert result.status == "success"
    assert result.public_access is True


# ==============================================================================
# Unit Tests: Settings & Configuration Alignment
# ==============================================================================

def test_settings_load_defaults_without_credentials():
    """Verify that Settings can be instantiated when no platform credentials are provided."""
    from app.config import Settings

    test_settings = Settings(_env_file=None)

    # Server defaults
    assert test_settings.APP_NAME == "Automated Multi-Platform Posting System"
    assert test_settings.PORT == 4000
    assert test_settings.HOST == "0.0.0.0"

    # Sensible platform defaults
    assert test_settings.REDDIT_USER_AGENT == "AutomatedPoster/1.0.0"
    assert test_settings.REDDIT_SUBREDDIT == "test"
    assert test_settings.LINKEDIN_VERSION == "202611"
    assert test_settings.MASTODON_INSTANCE_URL == "https://mastodon.social"

    # Missing optional credentials must default to None without causing errors
    assert test_settings.TELEGRAM_BOT_TOKEN is None
    assert test_settings.TELEGRAM_CHAT_ID is None
    assert test_settings.DISCORD_WEBHOOK_URL is None
    assert test_settings.REDDIT_CLIENT_ID is None
    assert test_settings.REDDIT_CLIENT_SECRET is None
    assert test_settings.REDDIT_REFRESH_TOKEN is None
    assert test_settings.REDDIT_ACCESS_TOKEN is None
    assert test_settings.LINKEDIN_ACCESS_TOKEN is None
    assert test_settings.LINKEDIN_AUTHOR_URN is None
    assert test_settings.MASTODON_ACCESS_TOKEN is None


def test_settings_override_via_arguments():
    """Verify that settings can be customized through constructor parameters."""
    from app.config import Settings

    custom_settings = Settings(
        _env_file=None,
        LINKEDIN_VERSION="202701",
        REDDIT_SUBREDDIT="dxora_announcements",
        TELEGRAM_CHAT_ID="@dxora_official",
        MASTODON_INSTANCE_URL="https://mstdn.io",
    )

    assert custom_settings.LINKEDIN_VERSION == "202701"
    assert custom_settings.REDDIT_SUBREDDIT == "dxora_announcements"
    assert custom_settings.TELEGRAM_CHAT_ID == "@dxora_official"
    assert custom_settings.MASTODON_INSTANCE_URL == "https://mstdn.io"


def test_settings_loaded_from_environment(monkeypatch):
    """Verify that environment variables are correctly loaded into Settings."""
    from app.config import Settings

    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "mock_telegram_token_123")
    monkeypatch.setenv("REDDIT_REFRESH_TOKEN", "mock_refresh_token_xyz")
    monkeypatch.setenv("LINKEDIN_VERSION", "202706")

    env_settings = Settings(_env_file=None)

    assert env_settings.APP_ENV == "staging"
    assert env_settings.TELEGRAM_BOT_TOKEN == "mock_telegram_token_123"
    assert env_settings.REDDIT_REFRESH_TOKEN == "mock_refresh_token_xyz"
    assert env_settings.LINKEDIN_VERSION == "202706"


def test_reddit_credentials_exclude_username_and_password():
    """Verify that REDDIT_USERNAME and REDDIT_PASSWORD are not part of the Settings model."""
    from app.config import Settings

    assert "REDDIT_USERNAME" not in Settings.model_fields
    assert "REDDIT_PASSWORD" not in Settings.model_fields

    test_settings = Settings(_env_file=None)
    assert not hasattr(test_settings, "REDDIT_USERNAME")
    assert not hasattr(test_settings, "REDDIT_PASSWORD")


def test_linkedin_version_is_configurable(monkeypatch):
    """Verify that LINKEDIN_VERSION can be overridden via both env and constructor."""
    from app.config import Settings

    # Default
    default_settings = Settings(_env_file=None)
    assert default_settings.LINKEDIN_VERSION == "202611"

    # Override via environment variable
    monkeypatch.setenv("LINKEDIN_VERSION", "202501")
    env_settings = Settings(_env_file=None)
    assert env_settings.LINKEDIN_VERSION == "202501"

    # Override via constructor argument
    arg_settings = Settings(_env_file=None, LINKEDIN_VERSION="202712")
    assert arg_settings.LINKEDIN_VERSION == "202712"


# ==============================================================================
# Unit Tests: TelegramPlatform Integration (Mocked HTTPX)
# ==============================================================================

@pytest.mark.asyncio
async def test_telegram_missing_credentials():
    """Verify that TelegramPlatform handles missing credentials gracefully without crashing."""
    from app.platforms.telegram import TelegramPlatform

    platform = TelegramPlatform(bot_token=None, chat_id=None)
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Telegram"
    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date is None
    assert result.time is None
    assert "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID" in result.error


@pytest.mark.asyncio
async def test_telegram_successful_publication_public_channel(monkeypatch):
    """Verify successful Telegram publication with public channel URL generation."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    fake_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    async def mock_post(self, url, *args, **kwargs):
        assert fake_token in url
        return httpx.Response(
            status_code=200,
            json={
                "ok": True,
                "result": {
                    "message_id": 1042,
                    "chat": {
                        "id": -1001234567890,
                        "title": "Dxora Public Channel",
                        "username": "dxora_public",
                        "type": "channel",
                    },
                    "date": 1731931200,
                    "text": "Check out our platform https://example.com",
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token=fake_token, chat_id="@dxora_public")
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Telegram"
    assert result.status == "success"
    assert result.posted_url == "https://t.me/dxora_public/1042"
    assert result.public_access is True
    assert result.date == datetime.date(2024, 11, 18)
    assert result.time == datetime.time(12, 0, 0)
    assert result.error is None


@pytest.mark.asyncio
async def test_telegram_api_rejection(monkeypatch):
    """Verify that Telegram API business-level errors (ok: false) are captured cleanly."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    fake_token = "secret_bot_token"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "ok": False,
                "error_code": 400,
                "description": "Bad Request: chat not found",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token=fake_token, chat_id="@invalid_channel")
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is False
    assert "Telegram API error: Bad Request: chat not found" in result.error
    assert fake_token not in result.error


@pytest.mark.asyncio
async def test_telegram_http_status_error(monkeypatch):
    """Verify that HTTP 4xx/5xx status errors are handled without unhandled exceptions."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    fake_token = "secret_bot_token"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=403,
            json={
                "ok": False,
                "error_code": 403,
                "description": "Forbidden: bot was blocked by the user",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token=fake_token, chat_id="12345678")
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.status == "failed"
    assert "HTTP 403 error" in result.error
    assert "Forbidden: bot was blocked by the user" in result.error
    assert fake_token not in result.error


@pytest.mark.asyncio
async def test_telegram_network_error(monkeypatch):
    """Verify that network/connection errors are handled gracefully."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.ConnectError("Connection refused by peer", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token="test_token", chat_id="@dxora")
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.status == "failed"
    assert "Telegram network error" in result.error


@pytest.mark.asyncio
async def test_telegram_request_timeout(monkeypatch):
    """Verify that request timeout exceptions are caught cleanly."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.TimeoutException("Read operation timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token="test_token", chat_id="@dxora")
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.status == "failed"
    assert result.error == "Telegram request timed out."


@pytest.mark.asyncio
async def test_telegram_public_channel_url_generation_from_chat_id(monkeypatch):
    """Verify public channel URL generation when chat_id starts with @ even if chat.username is omitted."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "ok": True,
                "result": {
                    "message_id": 555,
                    "chat": {"id": -10012345},  # username omitted in response
                    "date": 1731931200,
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token="token", chat_id="@my_custom_channel")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.public_access is True
    assert result.posted_url == "https://t.me/my_custom_channel/555"


@pytest.mark.asyncio
async def test_telegram_non_public_destination_behavior(monkeypatch):
    """Verify that non-public destinations (numeric chat ID without username) have public_access=False and no posted_url."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "ok": True,
                "result": {
                    "message_id": 888,
                    "chat": {"id": -1009999999999, "type": "supergroup"},  # private group, no username
                    "date": 1731931200,
                },
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token="token", chat_id="-1009999999999")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.public_access is False
    assert result.posted_url is None
    assert result.error is None


@pytest.mark.asyncio
async def test_telegram_token_sanitization_in_errors(monkeypatch):
    """Verify that sensitive bot tokens are never leaked into error messages."""
    import httpx
    from app.platforms.telegram import TelegramPlatform

    secret_token = "987654321:SECRET_TOKEN_XYZ_123"

    async def mock_post(self, url, *args, **kwargs):
        # Simulate an exception string that accidentally includes the full request URL
        raise httpx.RequestError(
            f"Failed to connect to https://api.telegram.org/bot{secret_token}/sendMessage",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = TelegramPlatform(bot_token=secret_token, chat_id="@test")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert secret_token not in result.error
    assert "[REDACTED_BOT_TOKEN]" in result.error


# ==============================================================================
# Unit Tests: DiscordPlatform Integration (Mocked HTTPX)
# ==============================================================================

@pytest.mark.asyncio
async def test_discord_missing_credentials():
    """Verify that DiscordPlatform handles missing webhook URL gracefully."""
    from app.platforms.discord import DiscordPlatform

    platform = DiscordPlatform(webhook_url=None)
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Discord"
    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date is None
    assert result.time is None
    assert "Missing DISCORD_WEBHOOK_URL" in result.error


@pytest.mark.asyncio
async def test_discord_successful_publication_with_guild_id(monkeypatch):
    """Verify successful Discord publication with guild and channel IDs."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    fake_url = "https://discord.com/api/webhooks/123456789/dummy_token"

    async def mock_post(self, url, *args, **kwargs):
        assert "wait=true" in url
        return httpx.Response(
            status_code=200,
            json={
                "id": "1307682949281726514",
                "channel_id": "1199382103982910291",
                "guild_id": "1199382000000000000",
                "content": "Check out our platform https://example.com",
                "timestamp": "2026-11-18T12:00:00.000000+00:00",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url=fake_url)
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Discord"
    assert result.status == "success"
    assert result.posted_url == "https://discord.com/channels/1199382000000000000/1199382103982910291/1307682949281726514"
    assert result.public_access is False
    assert result.date == datetime.date(2026, 11, 18)
    assert result.time == datetime.time(12, 0, 0)
    assert result.error is None


@pytest.mark.asyncio
async def test_discord_successful_publication_without_guild_id(monkeypatch):
    """Verify that omitting guild_id sets posted_url=None and does not invent a message URL."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    fake_url = "https://discord.com/api/webhooks/123456789/dummy_token"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "1307682949281726514",
                "channel_id": "1199382103982910291",
                "content": "Check out our platform https://example.com",
                "timestamp": "2026-11-18T12:00:00.000000+00:00",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url=fake_url)
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date == datetime.date(2026, 11, 18)
    assert result.time == datetime.time(12, 0, 0)


@pytest.mark.asyncio
async def test_discord_missing_timestamp_produces_none(monkeypatch):
    """Verify that a missing timestamp sets date=None and time=None without substituting system time."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "1307682949281726514",
                "channel_id": "1199382103982910291",
                "guild_id": "1199382000000000000",
                "content": "Hello",
                # timestamp omitted
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url="https://discord.com/api/webhooks/1/token")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.date is None
    assert result.time is None


@pytest.mark.asyncio
async def test_discord_invalid_timestamp_produces_none(monkeypatch):
    """Verify that an invalid timestamp sets date=None and time=None without raising errors."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "1307682949281726514",
                "channel_id": "1199382103982910291",
                "guild_id": "1199382000000000000",
                "content": "Hello",
                "timestamp": "not-a-valid-iso-timestamp",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url="https://discord.com/api/webhooks/1/token")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.date is None
    assert result.time is None


@pytest.mark.asyncio
async def test_discord_wait_true_query_param_handling(monkeypatch):
    """Verify that wait=false is replaced by wait=true while preserving other query parameters."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    input_url = "https://discord.com/api/webhooks/123/token?wait=false&thread_id=987&category=promo"
    captured_url = None

    async def mock_post(self, url, *args, **kwargs):
        nonlocal captured_url
        captured_url = url
        return httpx.Response(
            status_code=200,
            json={
                "id": "1307682949281726514",
                "channel_id": "1199382103982910291",
                "guild_id": "1199382000000000000",
                "timestamp": "2026-11-18T12:00:00.000000+00:00",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url=input_url)
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert captured_url is not None
    assert "wait=true" in captured_url
    assert "wait=false" not in captured_url
    assert "thread_id=987" in captured_url
    assert "category=promo" in captured_url



@pytest.mark.asyncio
async def test_discord_api_rejection_http_error(monkeypatch):
    """Verify that Discord HTTP errors (e.g. 401 Unauthorized) are handled cleanly."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    fake_url = "https://discord.com/api/webhooks/123456789/dummy_token"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=401,
            json={"message": "401: Unauthorized", "code": 0},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url=fake_url)
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "HTTP 401 error" in result.error
    assert "Unauthorized" in result.error
    assert result.posted_url is None


@pytest.mark.asyncio
async def test_discord_network_error(monkeypatch):
    """Verify that network errors while contacting Discord are caught gracefully."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.ConnectError("Network unreachable", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url="https://discord.com/api/webhooks/1/token")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Discord network error" in result.error


@pytest.mark.asyncio
async def test_discord_request_timeout(monkeypatch):
    """Verify that request timeouts are caught cleanly."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.TimeoutException("Read timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url="https://discord.com/api/webhooks/1/token")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert result.error == "Discord request timed out."


@pytest.mark.asyncio
async def test_discord_missing_message_or_channel_id(monkeypatch):
    """Verify that responses missing message id or channel id return failed status."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"content": "Hello without id"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url="https://discord.com/api/webhooks/1/token")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Missing 'id' or 'channel_id'" in result.error
    assert result.posted_url is None


@pytest.mark.asyncio
async def test_discord_malformed_json_response(monkeypatch):
    """Verify that non-JSON response bodies return failed status without crashing."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            text="<html>Bad Gateway</html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url="https://discord.com/api/webhooks/1/token")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Failed to parse JSON" in result.error


@pytest.mark.asyncio
async def test_discord_webhook_token_sanitization(monkeypatch):
    """Verify that the webhook secret token is never exposed in error messages."""
    import httpx
    from app.platforms.discord import DiscordPlatform

    secret_token = "ultra_confidential_webhook_secret_998877"
    full_url = f"https://discord.com/api/webhooks/123456789/{secret_token}"

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.RequestError(
            f"Failed to post to {full_url}",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = DiscordPlatform(webhook_url=full_url)
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert secret_token not in result.error
    assert "[REDACTED_DISCORD" in result.error


# ==============================================================================
# Unit Tests: RedditPlatform Integration (Mocked HTTPX)
# ==============================================================================

@pytest.mark.asyncio
async def test_reddit_missing_credentials():
    """Verify that RedditPlatform fails gracefully when credentials are not configured."""
    from app.platforms.reddit import RedditPlatform

    platform = RedditPlatform(
        client_id=None,
        client_secret=None,
        refresh_token=None,
        access_token=None,
    )
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Reddit"
    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date is None
    assert result.time is None
    assert "Missing required credentials" in result.error


@pytest.mark.asyncio
async def test_reddit_successful_token_refresh_and_submission(monkeypatch):
    """Verify successful OAuth token refresh followed by post submission."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    token_url_called = False
    submit_url_called = False

    async def mock_post(self, url, *args, **kwargs):
        nonlocal token_url_called, submit_url_called
        if "access_token" in url:
            token_url_called = True
            assert kwargs.get("auth") == ("test_client_id", "test_client_secret")
            assert kwargs.get("data", {}).get("grant_type") == "refresh_token"
            return httpx.Response(
                status_code=200,
                json={
                    "access_token": "mocked_reddit_access_token_123",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "scope": "submit identity",
                },
                request=httpx.Request("POST", url),
            )
        elif "submit" in url:
            submit_url_called = True
            headers = kwargs.get("headers", {})
            assert headers.get("Authorization") == "Bearer mocked_reddit_access_token_123"
            payload = kwargs.get("data", {})
            assert payload.get("sr") == "test"
            assert payload.get("kind") == "self"
            assert "https://example.com" in payload.get("text")
            return httpx.Response(
                status_code=200,
                json={
                    "json": {
                        "errors": [],
                        "data": {
                            "url": "https://www.reddit.com/r/test/comments/1gxabc/online_platform_announcement/",
                            "id": "1gxabc",
                            "name": "t3_1gxabc",
                            "created_utc": 1731931200,
                        },
                    }
                },
                request=httpx.Request("POST", url),
            )
        raise RuntimeError(f"Unexpected URL: {url}")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(
        client_id="test_client_id",
        client_secret="test_client_secret",
        refresh_token="test_refresh_token",
        access_token=None,
        subreddit="r/test",
    )
    result = await platform.publish(
        message="Online Platform Announcement\nCheck out our platform https://example.com",
        url="https://example.com",
    )

    assert token_url_called is True
    assert submit_url_called is True
    assert result.platform == "Reddit"
    assert result.status == "success"
    assert result.posted_url == "https://www.reddit.com/r/test/comments/1gxabc/online_platform_announcement/"
    assert result.public_access is False
    assert result.date == datetime.date(2024, 11, 18)
    assert result.time == datetime.time(12, 0, 0)
    assert result.error is None


@pytest.mark.asyncio
async def test_reddit_successful_direct_token_submission(monkeypatch):
    """Verify that providing REDDIT_ACCESS_TOKEN skips token refresh and submits directly."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    token_refreshed = False

    async def mock_post(self, url, *args, **kwargs):
        nonlocal token_refreshed
        if "access_token" in url:
            token_refreshed = True
            raise RuntimeError("Should not call token refresh when access_token is provided")
        return httpx.Response(
            status_code=200,
            json={
                "json": {
                    "errors": [],
                    "data": {
                        "url": "https://www.reddit.com/r/test/comments/999/direct_token/",
                        "id": "999",
                    },
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(
        access_token="direct_access_token_xyz",
        subreddit="test",
    )
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert token_refreshed is False
    assert result.status == "success"
    assert result.posted_url == "https://www.reddit.com/r/test/comments/999/direct_token/"
    assert result.public_access is False


@pytest.mark.asyncio
async def test_reddit_authentication_failure_during_token_refresh(monkeypatch):
    """Verify that token refresh failure returns failed result with sanitized error."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    secret_key = "my_private_secret_key_88"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=401,
            text=f"Unauthorized: Invalid client secret {secret_key}",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(
        client_id="cid",
        client_secret=secret_key,
        refresh_token="ref_tok",
    )
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Reddit authentication failed" in result.error
    assert secret_key not in result.error
    assert "[REDACTED_CREDENTIAL]" in result.error


@pytest.mark.asyncio
async def test_reddit_api_rejection_errors(monkeypatch):
    """Verify that Reddit API business-level rejection errors are captured."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    async def mock_post(self, url, *args, **kwargs):
        if "access_token" in url:
            return httpx.Response(
                status_code=200,
                json={"access_token": "valid_token"},
                request=httpx.Request("POST", url),
            )
        return httpx.Response(
            status_code=200,
            json={
                "json": {
                    "errors": [
                        ["RATELIMIT", "You are doing that too much. Try again in 5 minutes.", "ratelimit"]
                    ]
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(
        access_token="valid_token",
        subreddit="test",
    )
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Reddit API rejection" in result.error
    assert "You are doing that too much" in result.error
    assert result.posted_url is None


@pytest.mark.asyncio
async def test_reddit_network_error(monkeypatch):
    """Verify that network errors during Reddit requests are handled gracefully."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.ConnectError("Failed to reach Reddit gateway", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(access_token="tok", subreddit="test")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Reddit network error" in result.error


@pytest.mark.asyncio
async def test_reddit_request_timeout(monkeypatch):
    """Verify that timeouts during Reddit requests return a clean failure result."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.TimeoutException("Reddit connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(access_token="tok", subreddit="test")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert result.error == "Reddit request timed out."


@pytest.mark.asyncio
async def test_reddit_malformed_api_response(monkeypatch):
    """Verify that unexpected response formats missing 'json' root are trapped."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"unexpected": "structure"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(access_token="tok", subreddit="test")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Missing 'json' root object" in result.error


@pytest.mark.asyncio
async def test_reddit_missing_post_url_in_response(monkeypatch):
    """Verify that responses missing the post URL fail cleanly without guessing URLs."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "json": {
                    "errors": [],
                    "data": {
                        "id": "abc123",
                        # url omitted
                    },
                }
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(access_token="tok", subreddit="test")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "did not provide a published post URL" in result.error
    assert result.posted_url is None


@pytest.mark.asyncio
async def test_reddit_token_and_secret_sanitization(monkeypatch):
    """Verify that refresh token and client secret are scrubbed from error messages."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    secret_key = "super_classified_secret_key"
    refresh_tok = "super_classified_refresh_token"

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.RequestError(
            f"Error occurred with secret={secret_key} and refresh={refresh_tok}",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(
        client_id="cid",
        client_secret=secret_key,
        refresh_token=refresh_tok,
    )
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert secret_key not in result.error
    assert refresh_tok not in result.error
    assert "[REDACTED_CREDENTIAL]" in result.error


@pytest.mark.asyncio
async def test_reddit_active_access_token_sanitization(monkeypatch):
    """Verify that a newly generated access token from refresh flow is redacted if leaked in submission errors."""
    import httpx
    from app.platforms.reddit import RedditPlatform

    refreshed_token = "newly_generated_bearer_token_abc999"

    async def mock_post(self, url, *args, **kwargs):
        if "access_token" in url:
            return httpx.Response(
                status_code=200,
                json={"access_token": refreshed_token, "expires_in": 3600},
                request=httpx.Request("POST", url),
            )
        # Simulate an HTTP error whose response body or request error text echoes the active token
        raise httpx.RequestError(
            f"Failed to post with Authorization: Bearer {refreshed_token}",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = RedditPlatform(
        client_id="cid",
        client_secret="csecret",
        refresh_token="reftok",
        access_token=None,  # Forces refresh flow to generate active_token
    )
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert refreshed_token not in result.error
    assert "[REDACTED_CREDENTIAL]" in result.error


def test_reddit_subreddit_normalization():
    """Verify that normalize_subreddit strips only 'r/' prefix and preserves subreddits starting with 'r'."""
    from app.platforms.reddit import normalize_subreddit

    assert normalize_subreddit("r/test") == "test"
    assert normalize_subreddit("R/TEST") == "TEST"
    assert normalize_subreddit("  r/programming  ") == "programming"
    assert normalize_subreddit("test") == "test"
    # Ensure subreddits starting with 'r' are preserved and not stripped by character sets
    assert normalize_subreddit("rust") == "rust"
    assert normalize_subreddit("r/rust") == "rust"
    assert normalize_subreddit("reactjs") == "reactjs"
    assert normalize_subreddit("r/reactjs") == "reactjs"
    assert normalize_subreddit("ruby") == "ruby"
    assert normalize_subreddit("") == "test"
    assert normalize_subreddit(None) == "test"


# ==============================================================================
# Unit Tests: LinkedInPlatform Integration (Mocked HTTPX)
# ==============================================================================

@pytest.mark.asyncio
async def test_linkedin_missing_credentials():
    """Verify that LinkedInPlatform fails gracefully when access token or author URN is missing."""
    from app.platforms.linkedin import LinkedInPlatform

    platform = LinkedInPlatform(access_token=None, author_urn=None)
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "LinkedIn"
    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date is None
    assert result.time is None
    assert "Missing required credentials" in result.error


@pytest.mark.asyncio
async def test_linkedin_successful_member_post(monkeypatch):
    """Verify successful publication for a member author with x-restli-id header and timestamp."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    captured_request = {}

    async def mock_post(self, url, *args, **kwargs):
        captured_request["url"] = url
        captured_request["headers"] = kwargs.get("headers", {})
        captured_request["json"] = kwargs.get("json", {})
        return httpx.Response(
            status_code=201,
            headers={
                "x-restli-id": "urn:li:share:7123456789012345678",
                "Content-Type": "application/json",
            },
            json={"createdAt": 1731931200000},  # 2024-11-18 12:00:00 UTC in ms
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(
        access_token="test_linkedin_access_token_123",
        author_urn="urn:li:person:abcdef123",
        linkedin_version="202611",
    )
    result = await platform.publish(
        message="New release announced! https://example.com",
        url="https://example.com",
    )

    assert result.platform == "LinkedIn"
    assert result.status == "success"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date == datetime.date(2024, 11, 18)
    assert result.time == datetime.time(12, 0, 0)
    assert result.error is None

    # Endpoint and headers verification
    assert captured_request["url"] == "https://api.linkedin.com/rest/posts"
    assert captured_request["headers"]["Authorization"] == "Bearer test_linkedin_access_token_123"
    assert captured_request["headers"]["LinkedIn-Version"] == "202611"
    assert captured_request["headers"]["X-Restli-Protocol-Version"] == "2.0.0"
    assert captured_request["headers"]["Content-Type"] == "application/json"

    # JSON payload verification
    payload = captured_request["json"]
    assert payload["author"] == "urn:li:person:abcdef123"
    assert payload["commentary"] == "New release announced! https://example.com"
    assert payload["visibility"] == "PUBLIC"
    assert payload["lifecycleState"] == "PUBLISHED"
    assert payload["isReshareDisabledByAuthor"] is False
    assert payload["distribution"] == {
        "feedDistribution": "MAIN_FEED",
        "targetEntities": [],
        "thirdPartyDistributionChannels": [],
    }


@pytest.mark.asyncio
async def test_linkedin_successful_organization_post(monkeypatch):
    """Verify that an organization URN author is correctly supported in the payload."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    captured_payload = None

    async def mock_post(self, url, *args, **kwargs):
        nonlocal captured_payload
        captured_payload = kwargs.get("json", {})
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:ugcPost:9988776655"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(
        access_token="org_token",
        author_urn="urn:li:organization:12345678",
    )
    result = await platform.publish("Company update https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.posted_url is None
    assert result.public_access is False
    assert captured_payload is not None
    assert captured_payload["author"] == "urn:li:organization:12345678"


@pytest.mark.asyncio
async def test_linkedin_configurable_api_version(monkeypatch):
    """Verify that a custom LinkedIn API version is passed in the LinkedIn-Version header."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    captured_version = None

    async def mock_post(self, url, *args, **kwargs):
        nonlocal captured_version
        captured_version = kwargs.get("headers", {}).get("LinkedIn-Version")
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:111"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(
        access_token="tok",
        author_urn="urn:li:person:1",
        linkedin_version="202706",
    )
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert captured_version == "202706"


@pytest.mark.asyncio
async def test_linkedin_http_401_unauthorized(monkeypatch):
    """Verify that HTTP 401 returns a failed PlatformResult with sanitized error description."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    secret_token = "confidential_linkedin_token_xyz"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=401,
            json={"message": f"Token {secret_token} expired or invalid", "status": 401},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token=secret_token, author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "authentication failed" in result.error.lower()
    assert "401" in result.error
    assert secret_token not in result.error
    assert "[REDACTED_ACCESS_TOKEN]" in result.error


@pytest.mark.asyncio
async def test_linkedin_http_403_forbidden(monkeypatch):
    """Verify that HTTP 403 permission failures are clearly reported."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=403,
            json={"message": "Not enough permissions to access /posts", "status": 403},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "permission denied" in result.error.lower()
    assert "403" in result.error
    assert "Not enough permissions" in result.error


@pytest.mark.asyncio
async def test_linkedin_http_400_bad_request(monkeypatch):
    """Verify that HTTP 400 validation errors return a clean failed result."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=400,
            json={"message": "Invalid URN format for author", "status": 400},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="invalid_urn")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "validation error" in result.error.lower()
    assert "400" in result.error
    assert "Invalid URN" in result.error


@pytest.mark.asyncio
async def test_linkedin_other_http_errors(monkeypatch):
    """Verify that other HTTP errors (e.g. 500) are handled gracefully."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=500,
            text="Internal Server Error",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "HTTP 500 error" in result.error


@pytest.mark.asyncio
async def test_linkedin_network_error(monkeypatch):
    """Verify that connection/network errors are caught cleanly."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.ConnectError("Could not resolve host api.linkedin.com", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "LinkedIn network error" in result.error


@pytest.mark.asyncio
async def test_linkedin_request_timeout(monkeypatch):
    """Verify that request timeouts return a clean failure result."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.TimeoutException("Read timeout on LinkedIn gateway")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert result.error == "LinkedIn request timed out."


@pytest.mark.asyncio
async def test_linkedin_missing_post_identifier(monkeypatch):
    """Verify that responses missing the post identifier in headers and body return failure."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=201,
            headers={"Content-Type": "application/json"},
            json={},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "did not contain a valid post identifier" in result.error
    assert result.posted_url is None


@pytest.mark.asyncio
async def test_linkedin_malformed_response(monkeypatch):
    """Verify that non-JSON response bodies without header post ID return failure without crashing."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            text="<html>Service Unavailable</html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Failed to parse JSON" in result.error


@pytest.mark.asyncio
async def test_linkedin_access_token_sanitization(monkeypatch):
    """Verify that the secret LinkedIn access token is never leaked in error messages."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    confidential_token = "secret_access_token_linkedin_987654"

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.RequestError(
            f"Failed to send request with Authorization: Bearer {confidential_token}",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = LinkedInPlatform(access_token=confidential_token, author_urn="urn:li:person:1")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert confidential_token not in result.error
    assert "[REDACTED_ACCESS_TOKEN]" in result.error


@pytest.mark.asyncio
async def test_linkedin_timestamp_handling(monkeypatch):
    """Verify ISO string timestamp parsing and missing timestamp producing None."""
    import httpx
    from app.platforms.linkedin import LinkedInPlatform

    # 1. Valid ISO string timestamp
    async def mock_post_iso(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:123"},
            json={"createdAt": "2026-11-18T14:30:00Z"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_iso)
    platform = LinkedInPlatform(access_token="tok", author_urn="urn:li:person:1")
    result_iso = await platform.publish("Check https://example.com", "https://example.com")

    assert result_iso.status == "success"
    assert result_iso.date == datetime.date(2026, 11, 18)
    assert result_iso.time == datetime.time(14, 30, 0)

    # 2. Missing timestamp in response produces None without inventing system time
    async def mock_post_no_ts(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=201,
            headers={"x-restli-id": "urn:li:share:456"},
            content=b"",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_no_ts)
    result_no_ts = await platform.publish("Check https://example.com", "https://example.com")

    assert result_no_ts.status == "success"
    assert result_no_ts.date is None
    assert result_no_ts.time is None


# ==============================================================================
# Unit Tests: MastodonPlatform Integration (Mocked HTTPX)
# ==============================================================================

@pytest.mark.asyncio
async def test_mastodon_missing_credentials():
    """Verify that MastodonPlatform fails gracefully when access token is missing."""
    from app.platforms.mastodon import MastodonPlatform

    platform = MastodonPlatform(access_token=None)
    result = await platform.publish(
        message="Check out our platform https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Mastodon"
    assert result.status == "failed"
    assert result.posted_url is None
    assert result.public_access is False
    assert result.date is None
    assert result.time is None
    assert "Missing required credentials" in result.error


@pytest.mark.asyncio
async def test_mastodon_successful_public_status_creation(monkeypatch):
    """Verify successful status creation with public visibility, valid URL, headers, and timestamp."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    captured_request = {}

    async def mock_post(self, url, *args, **kwargs):
        captured_request["url"] = url
        captured_request["headers"] = kwargs.get("headers", {})
        captured_request["json"] = kwargs.get("json", {})
        return httpx.Response(
            status_code=200,
            json={
                "id": "113504829104829104",
                "created_at": "2026-11-18T12:00:00.000Z",
                "visibility": "public",
                "url": "https://mastodon.social/@dxora/113504829104829104",
                "uri": "https://mastodon.social/users/dxora/statuses/113504829104829104",
                "content": "<p>Announcing Dxora platform! https://example.com</p>",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(
        instance_url="https://mastodon.social",
        access_token="test_mastodon_access_token_123",
    )
    result = await platform.publish(
        message="Announcing Dxora platform! https://example.com",
        url="https://example.com",
    )

    assert result.platform == "Mastodon"
    assert result.status == "success"
    assert result.posted_url == "https://mastodon.social/@dxora/113504829104829104"
    assert result.public_access is True
    assert result.date == datetime.date(2026, 11, 18)
    assert result.time == datetime.time(12, 0, 0)
    assert result.error is None

    # Verify endpoint, headers, and payload
    assert captured_request["url"] == "https://mastodon.social/api/v1/statuses"
    assert captured_request["headers"]["Authorization"] == "Bearer test_mastodon_access_token_123"
    assert captured_request["headers"]["Content-Type"] == "application/json"
    assert captured_request["json"] == {
        "status": "Announcing Dxora platform! https://example.com",
        "visibility": "public",
    }


def test_mastodon_url_normalization_function():
    """Verify that normalize_instance_url safely handles missing schemes, trailing slashes, and spaces."""
    from app.platforms.mastodon import normalize_instance_url

    assert normalize_instance_url("https://mastodon.social") == "https://mastodon.social"
    assert normalize_instance_url("https://mastodon.social/") == "https://mastodon.social"
    assert normalize_instance_url("https://mastodon.social///") == "https://mastodon.social"
    assert normalize_instance_url("mastodon.online") == "https://mastodon.online"
    assert normalize_instance_url("  fosstodon.org/  ") == "https://fosstodon.org"
    assert normalize_instance_url("http://local-fediverse:3000/") == "http://local-fediverse:3000"
    assert normalize_instance_url("") == "https://mastodon.social"
    assert normalize_instance_url(None) == "https://mastodon.social"


@pytest.mark.asyncio
async def test_mastodon_custom_instance_endpoint(monkeypatch):
    """Verify that custom instance URLs are normalized and contacted without double slashes."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    captured_url = None

    async def mock_post(self, url, *args, **kwargs):
        nonlocal captured_url
        captured_url = url
        return httpx.Response(
            status_code=200,
            json={
                "id": "999",
                "created_at": "2026-11-18T12:00:00.000Z",
                "visibility": "public",
                "url": "https://fosstodon.org/@dxora/999",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(
        instance_url="https://fosstodon.org///",
        access_token="tok",
    )
    result = await platform.publish("Custom instance https://example.com", "https://example.com")

    assert result.status == "success"
    assert captured_url == "https://fosstodon.org/api/v1/statuses"
    assert "//api" not in captured_url.replace("https://", "")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "returned_visibility,expected_public",
    [
        ("public", True),
        ("PUBLIC", True),
        ("unlisted", False),
        ("private", False),
        ("direct", False),
        ("unknown_custom_scope", False),
        (None, False),
    ],
)
async def test_mastodon_visibility_handling(monkeypatch, returned_visibility, expected_public):
    """Verify that public_access is True ONLY when visibility is public, and False for unlisted/private/direct/unknown."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        payload = {
            "id": "12345",
            "url": "https://mastodon.social/@test/12345",
        }
        if returned_visibility is not None:
            payload["visibility"] = returned_visibility
        return httpx.Response(
            status_code=200,
            json=payload,
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.public_access is expected_public


@pytest.mark.asyncio
async def test_mastodon_http_401_unauthorized(monkeypatch):
    """Verify that HTTP 401 returns failure with sanitized error message."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    secret_token = "confidential_mastodon_token_abc123"

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=401,
            json={"error": f"The access token {secret_token} is invalid"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token=secret_token)
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "authentication failed" in result.error.lower()
    assert "401" in result.error
    assert secret_token not in result.error
    assert "[REDACTED_ACCESS_TOKEN]" in result.error


@pytest.mark.asyncio
async def test_mastodon_http_403_forbidden(monkeypatch):
    """Verify that HTTP 403 permission failures are clearly reported."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=403,
            json={"error": "This action requires the write:statuses scope."},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "permission denied" in result.error.lower()
    assert "403" in result.error
    assert "write:statuses" in result.error


@pytest.mark.asyncio
async def test_mastodon_http_422_validation_error(monkeypatch):
    """Verify that HTTP 422 validation errors are clearly reported."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=422,
            json={"error": "Validation failed: Text is too long"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "validation error" in result.error.lower()
    assert "422" in result.error
    assert "Validation failed" in result.error


@pytest.mark.asyncio
async def test_mastodon_other_http_errors(monkeypatch):
    """Verify that generic HTTP errors (e.g. 503 Service Unavailable) are handled cleanly."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=503,
            text="Service Temporarily Unavailable",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "HTTP 503 error" in result.error


@pytest.mark.asyncio
async def test_mastodon_network_error(monkeypatch):
    """Verify that network errors while contacting Mastodon instance are handled gracefully."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.ConnectError("Instance connection refused", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Mastodon network error" in result.error


@pytest.mark.asyncio
async def test_mastodon_request_timeout(monkeypatch):
    """Verify that request timeouts return a clean failure result."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.TimeoutException("Connection to Mastodon instance timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert result.error == "Mastodon request timed out."


@pytest.mark.asyncio
async def test_mastodon_malformed_response(monkeypatch):
    """Verify that non-JSON response bodies return failure without crashing."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            text="<html>Bad Gateway</html>",
            headers={"Content-Type": "text/html"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "Failed to parse JSON" in result.error


@pytest.mark.asyncio
async def test_mastodon_missing_or_invalid_status_url(monkeypatch):
    """Verify that responses missing the status URL return failure without inventing URLs."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    async def mock_post(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={"id": "123", "created_at": "2026-11-18T12:00:00Z"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert "did not provide a valid status URL" in result.error
    assert result.posted_url is None


@pytest.mark.asyncio
async def test_mastodon_access_token_sanitization(monkeypatch):
    """Verify that the secret Mastodon access token is never leaked in error messages."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    secret_token = "ultra_confidential_mastodon_bearer_token_777"

    async def mock_post(self, url, *args, **kwargs):
        raise httpx.RequestError(
            f"Failed to post to Mastodon with Authorization: Bearer {secret_token}",
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    platform = MastodonPlatform(access_token=secret_token)
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "failed"
    assert secret_token not in result.error
    assert "[REDACTED_ACCESS_TOKEN]" in result.error


@pytest.mark.asyncio
async def test_mastodon_timestamp_parsing(monkeypatch):
    """Verify timestamp parsing for ISO 8601 strings and clean None fallback."""
    import httpx
    from app.platforms.mastodon import MastodonPlatform

    # 1. Valid timestamp
    async def mock_post_valid(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "123",
                "url": "https://mastodon.social/@test/123",
                "visibility": "public",
                "created_at": "2026-11-18T18:45:30.123456Z",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_valid)
    platform = MastodonPlatform(access_token="tok")
    result = await platform.publish("Check https://example.com", "https://example.com")

    assert result.status == "success"
    assert result.date == datetime.date(2026, 11, 18)
    assert result.time == datetime.time(18, 45, 30, 123456)

    # 2. Invalid or missing timestamp produces None without guessing system time
    async def mock_post_invalid(self, url, *args, **kwargs):
        return httpx.Response(
            status_code=200,
            json={
                "id": "456",
                "url": "https://mastodon.social/@test/456",
                "visibility": "public",
                "created_at": "invalid_date_format",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_invalid)
    result_invalid = await platform.publish("Check https://example.com", "https://example.com")

    assert result_invalid.status == "success"
    assert result_invalid.date is None
    assert result_invalid.time is None


# ==============================================================================
# Unit Tests: PostingService Orchestrator (Mocked Platforms)
# ==============================================================================

from app.platforms.base import BasePlatform


class _TestMockPlatform(BasePlatform):
    """Configurable mock platform for testing PostingService orchestration."""

    def __init__(
        self,
        name: str,
        status: str = "success",
        delay: float = 0.0,
        exc: Optional[Exception] = None,
        error_msg: Optional[str] = None,
    ) -> None:
        self._name = name
        self._status = status
        self._delay = delay
        self._exc = exc
        self._error_msg = error_msg
        self.call_count = 0

    @property
    def platform_name(self) -> str:
        return self._name

    async def publish(self, message: str, url: str) -> PlatformResult:
        import asyncio

        self.call_count += 1
        if self._delay > 0:
            await asyncio.sleep(self._delay)

        if self._exc:
            raise self._exc

        if self._status == "success":
            return PlatformResult(
                platform=self._name,
                status="success",
                posted_url=f"https://{self._name.lower()}.example.com/posts/101",
                public_access=True,
                date=datetime.date(2026, 11, 18),
                time=datetime.time(12, 0, 0),
                error=None,
            )
        return PlatformResult(
            platform=self._name,
            status="failed",
            posted_url=None,
            public_access=False,
            date=None,
            time=None,
            error=self._error_msg or f"{self._name} test error",
        )


def test_posting_service_default_platform_initialization():
    """Verify that PostingService default constructor initializes all 5 platforms in order."""
    from app.services.posting_service import PostingService

    service = PostingService()
    platform_names = [p.platform_name for p in service.platforms]
    assert platform_names == ["Telegram", "Discord", "Reddit", "LinkedIn", "Mastodon"]
    assert len(service.platforms) == 5


@pytest.mark.asyncio
async def test_posting_service_all_five_platforms_succeed():
    """Verify that PostingResponse.success is True when all five platforms report success."""
    from app.services.posting_service import PostingService

    platforms = [
        _TestMockPlatform("Telegram", status="success"),
        _TestMockPlatform("Discord", status="success"),
        _TestMockPlatform("Reddit", status="success"),
        _TestMockPlatform("LinkedIn", status="success"),
        _TestMockPlatform("Mastodon", status="success"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all(
        message="Launch announcement https://example.com",
        url="https://example.com",
    )

    assert response.success is True
    assert len(response.results) == 5
    assert [r.platform for r in response.results] == [
        "Telegram",
        "Discord",
        "Reddit",
        "LinkedIn",
        "Mastodon",
    ]
    for r in response.results:
        assert r.status == "success"
        assert r.error is None
        assert r.posted_url is not None


@pytest.mark.asyncio
async def test_posting_service_one_fails_four_succeed():
    """Verify that if one platform fails, overall success is False while all 5 results are returned."""
    from app.services.posting_service import PostingService

    platforms = [
        _TestMockPlatform("Telegram", status="success"),
        _TestMockPlatform("Discord", status="success"),
        _TestMockPlatform("Reddit", status="failed", error_msg="Reddit rate limit exceeded"),
        _TestMockPlatform("LinkedIn", status="success"),
        _TestMockPlatform("Mastodon", status="success"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5

    # Check Reddit failed while other 4 succeeded
    reddit_res = next(r for r in response.results if r.platform == "Reddit")
    assert reddit_res.status == "failed"
    assert "rate limit" in reddit_res.error

    success_platforms = [r.platform for r in response.results if r.status == "success"]
    assert success_platforms == ["Telegram", "Discord", "LinkedIn", "Mastodon"]


@pytest.mark.asyncio
async def test_posting_service_multiple_platforms_fail():
    """Verify that when multiple platforms fail, all results are gathered and success is False."""
    from app.services.posting_service import PostingService

    platforms = [
        _TestMockPlatform("Telegram", status="success"),
        _TestMockPlatform("Discord", status="failed", error_msg="Discord 401 Unauthorized"),
        _TestMockPlatform("Reddit", status="failed", error_msg="Reddit token expired"),
        _TestMockPlatform("LinkedIn", status="success"),
        _TestMockPlatform("Mastodon", status="failed", error_msg="Mastodon connection refused"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5

    successful = [r.platform for r in response.results if r.status == "success"]
    failed = [r.platform for r in response.results if r.status == "failed"]

    assert successful == ["Telegram", "LinkedIn"]
    assert failed == ["Discord", "Reddit", "Mastodon"]


@pytest.mark.asyncio
async def test_posting_service_all_five_platforms_fail():
    """Verify that when all five platforms fail, success is False and all 5 failure results are returned."""
    from app.services.posting_service import PostingService

    platforms = [
        _TestMockPlatform("Telegram", status="failed", error_msg="Telegram 1"),
        _TestMockPlatform("Discord", status="failed", error_msg="Discord 2"),
        _TestMockPlatform("Reddit", status="failed", error_msg="Reddit 3"),
        _TestMockPlatform("LinkedIn", status="failed", error_msg="LinkedIn 4"),
        _TestMockPlatform("Mastodon", status="failed", error_msg="Mastodon 5"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5
    assert all(r.status == "failed" for r in response.results)


@pytest.mark.asyncio
async def test_posting_service_unexpected_exception_isolation():
    """Verify that an adapter raising an unhandled exception is isolated and does not abort others."""
    from app.services.posting_service import PostingService

    crash_exc = RuntimeError("Catastrophic platform adapter failure!")
    platforms = [
        _TestMockPlatform("Telegram", status="success"),
        _TestMockPlatform("Discord", exc=crash_exc),  # Raises unhandled exception
        _TestMockPlatform("Reddit", status="success"),
        _TestMockPlatform("LinkedIn", status="success"),
        _TestMockPlatform("Mastodon", status="success"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5

    # Verify other 4 platforms ran to completion
    for p in platforms:
        assert p.call_count == 1

    discord_res = next(r for r in response.results if r.platform == "Discord")
    assert discord_res.status == "failed"
    assert "Catastrophic platform adapter failure" in discord_res.error
    assert "RuntimeError" in discord_res.error


@pytest.mark.asyncio
async def test_posting_service_deterministic_ordering_with_varying_latencies():
    """Verify that results remain in deterministic platform order despite varying async completion times."""
    from app.services.posting_service import PostingService

    # Provide reverse latencies so later platforms complete first
    platforms = [
        _TestMockPlatform("Telegram", delay=0.05),
        _TestMockPlatform("Discord", delay=0.01),
        _TestMockPlatform("Reddit", delay=0.04),
        _TestMockPlatform("LinkedIn", delay=0.02),
        _TestMockPlatform("Mastodon", delay=0.03),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is True
    assert len(response.results) == 5
    assert [r.platform for r in response.results] == [
        "Telegram",
        "Discord",
        "Reddit",
        "LinkedIn",
        "Mastodon",
    ]


@pytest.mark.asyncio
async def test_posting_service_publish_alias():
    """Verify that the publish alias method behaves identically to post_to_all."""
    from app.services.posting_service import PostingService

    platforms = [
        _TestMockPlatform("Telegram", status="success"),
        _TestMockPlatform("Discord", status="success"),
        _TestMockPlatform("Reddit", status="success"),
        _TestMockPlatform("LinkedIn", status="success"),
        _TestMockPlatform("Mastodon", status="success"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.publish("Check https://example.com", "https://example.com")

    assert response.success is True
    assert len(response.results) == 5


def test_posting_service_empty_injected_platform_list():
    """Verify that injecting an empty platform list raises a ValueError."""
    from app.services.posting_service import PostingService

    with pytest.raises(ValueError) as exc_info:
        PostingService(platforms=[])

    assert "empty" in str(exc_info.value).lower()
    assert "exactly 5 platforms" in str(exc_info.value).lower()


def test_posting_service_missing_platform():
    """Verify that omitting one or more required platforms raises a descriptive ValueError."""
    from app.services.posting_service import PostingService

    incomplete_platforms = [
        _TestMockPlatform("Telegram"),
        _TestMockPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
        # Mastodon is missing
    ]
    with pytest.raises(ValueError) as exc_info:
        PostingService(platforms=incomplete_platforms)

    assert "missing required platforms" in str(exc_info.value).lower()
    assert "Mastodon" in str(exc_info.value)


def test_posting_service_duplicate_platform():
    """Verify that providing duplicate platform adapters raises a ValueError."""
    from app.services.posting_service import PostingService

    duplicate_platforms = [
        _TestMockPlatform("Telegram"),
        _TestMockPlatform("Telegram"),  # Duplicate
        _TestMockPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
    ]
    with pytest.raises(ValueError) as exc_info:
        PostingService(platforms=duplicate_platforms)

    assert "duplicate platform" in str(exc_info.value).lower()
    assert "Telegram" in str(exc_info.value)


def test_posting_service_unexpected_platform_name():
    """Verify that injecting an unrecognized or unsupported platform name raises a ValueError."""
    from app.services.posting_service import PostingService

    unexpected_platforms = [
        _TestMockPlatform("Telegram"),
        _TestMockPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
        _TestMockPlatform("Twitter"),  # Unexpected platform
    ]
    with pytest.raises(ValueError) as exc_info:
        PostingService(platforms=unexpected_platforms)

    assert "unexpected platform 'twitter'" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_posting_service_incorrect_result_platform_name():
    """Verify that if an adapter returns a PlatformResult with a mismatched platform name, it is marked failed."""
    from app.services.posting_service import PostingService

    class _MismatchedResultPlatform(_TestMockPlatform):
        async def publish(self, message: str, url: str) -> PlatformResult:
            return PlatformResult(
                platform="Discord",  # Mismatched name! Should be Telegram
                status="success",
                posted_url="https://example.com/1",
                public_access=True,
                date=datetime.date(2026, 11, 18),
                time=datetime.time(12, 0, 0),
            )

    platforms = [
        _MismatchedResultPlatform("Telegram"),
        _TestMockPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
        _TestMockPlatform("Mastodon"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5

    telegram_res = next(r for r in response.results if r.platform == "Telegram")
    assert telegram_res.status == "failed"
    assert "mismatched platform name" in telegram_res.error.lower()


@pytest.mark.asyncio
async def test_posting_service_invalid_adapter_result():
    """Verify that non-PlatformResult return values (e.g. None or str) are converted to failed PlatformResult."""
    from app.services.posting_service import PostingService

    class _InvalidResultPlatform(_TestMockPlatform):
        async def publish(self, message: str, url: str):
            return "not_a_valid_platform_result_object"

    platforms = [
        _TestMockPlatform("Telegram"),
        _InvalidResultPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
        _TestMockPlatform("Mastodon"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5

    discord_res = next(r for r in response.results if r.platform == "Discord")
    assert discord_res.status == "failed"
    assert "invalid result object" in discord_res.error.lower()


@pytest.mark.asyncio
async def test_posting_service_exception_sanitization():
    """Verify that unexpected exceptions never expose bot tokens, webhook secrets, or bearer tokens."""
    from app.services.posting_service import PostingService

    leaked_bot_token = "bot987654:ABCDEF_secret_telegram_token"
    leaked_webhook = "https://discord.com/api/webhooks/1234567890/ultra_secret_webhook_token_999"
    leaked_bearer = "Bearer super_secret_access_token_linkedin_xyz"

    exc_text = (
        f"Critical error on gateway: bot_token={leaked_bot_token}, "
        f"webhook={leaked_webhook}, auth={leaked_bearer}"
    )

    platforms = [
        _TestMockPlatform("Telegram", exc=RuntimeError(exc_text)),
        _TestMockPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
        _TestMockPlatform("Mastodon"),
    ]
    service = PostingService(platforms=platforms)
    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    telegram_res = next(r for r in response.results if r.platform == "Telegram")
    assert telegram_res.status == "failed"

    # Ensure none of the sensitive tokens or full webhook URLs are leaked
    assert "ABCDEF_secret_telegram_token" not in telegram_res.error
    assert "ultra_secret_webhook_token_999" not in telegram_res.error
    assert "super_secret_access_token_linkedin_xyz" not in telegram_res.error
    assert "[REDACTED_" in telegram_res.error


@pytest.mark.asyncio
async def test_posting_service_safe_fallback_handling(monkeypatch):
    """Verify that exceptions escaping directly from asyncio.gather() are cleanly converted and sanitized."""
    import asyncio
    from app.services.posting_service import PostingService

    platforms = [
        _TestMockPlatform("Telegram"),
        _TestMockPlatform("Discord"),
        _TestMockPlatform("Reddit"),
        _TestMockPlatform("LinkedIn"),
        _TestMockPlatform("Mastodon"),
    ]
    service = PostingService(platforms=platforms)

    # Simulate asyncio.gather returning an unhandled Exception for the 3rd platform (Reddit)
    original_gather = asyncio.gather

    async def mock_gather(*tasks, **kwargs):
        results = await original_gather(*tasks, **kwargs)
        # Inject an Exception object as returned by return_exceptions=True
        results[2] = RuntimeError("Direct gather exception with Bearer secret_bearer_token_123")
        return results

    monkeypatch.setattr(asyncio, "gather", mock_gather)

    response = await service.post_to_all("Check https://example.com", "https://example.com")

    assert response.success is False
    assert len(response.results) == 5

    reddit_res = response.results[2]
    assert reddit_res.platform == "Reddit"
    assert reddit_res.status == "failed"
    assert "secret_bearer_token_123" not in reddit_res.error
    assert "[REDACTED_TOKEN]" in reddit_res.error


@pytest.mark.asyncio
async def test_posting_service_exactly_five_results_for_valid_configurations():
    """Verify that any valid configuration returns exactly five PlatformResult items."""
    from app.services.posting_service import PostingService

    service = PostingService()
    assert len(service.platforms) == 5
    assert set(p.platform_name for p in service.platforms) == {
        "Telegram",
        "Discord",
        "Reddit",
        "LinkedIn",
        "Mastodon",
    }











