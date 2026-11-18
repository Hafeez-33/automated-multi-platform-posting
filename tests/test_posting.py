"""Tests for Pydantic schemas, input validation rules, and endpoint schema verification."""

import datetime
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




