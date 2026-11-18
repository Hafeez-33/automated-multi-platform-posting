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
    assert test_settings.LINKEDIN_VERSION == "202411"
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
    """Verify that settings can be customized through environment or constructor parameters."""
    from app.config import Settings

    custom_settings = Settings(
        _env_file=None,
        LINKEDIN_VERSION="202501",
        REDDIT_SUBREDDIT="dxora_announcements",
        TELEGRAM_CHAT_ID="@dxora_official",
        MASTODON_INSTANCE_URL="https://mstdn.io",
    )

    assert custom_settings.LINKEDIN_VERSION == "202501"
    assert custom_settings.REDDIT_SUBREDDIT == "dxora_announcements"
    assert custom_settings.TELEGRAM_CHAT_ID == "@dxora_official"
    assert custom_settings.MASTODON_INSTANCE_URL == "https://mstdn.io"


