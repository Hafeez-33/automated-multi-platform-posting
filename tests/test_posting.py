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
