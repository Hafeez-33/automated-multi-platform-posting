"""Pydantic schemas and input validation for the multi-platform posting system."""

import datetime
import re
from typing import List, Literal, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


# Regex pattern to identify URL candidates (including scheme:// and www. prefixes)
URL_CANDIDATE_REGEX = re.compile(
    r'(?:[a-zA-Z][a-zA-Z0-9+.-]*://|[wW]{3}\.)[^\s<>"\']*',
    re.IGNORECASE,
)


def _clean_url_token(raw_url: str) -> str:
    """
    Strip trailing punctuation commonly attached to URLs in prose text
    (e.g., periods, commas, trailing unclosed brackets).
    """
    url = raw_url
    while url:
        if url[-1] in '.,;!?"\'':
            url = url[:-1]
        elif url[-1] == ')' and '(' not in url:
            url = url[:-1]
        elif url[-1] == ']' and '[' not in url:
            url = url[:-1]
        elif url[-1] == '}' and '{' not in url:
            url = url[:-1]
        else:
            break
    return url


def extract_urls(text: str) -> List[str]:
    """Find and clean all candidate URLs in the given text."""
    matches = URL_CANDIDATE_REGEX.findall(text)
    cleaned: List[str] = []
    for m in matches:
        cleaned_url = _clean_url_token(m)
        if cleaned_url:
            cleaned.append(cleaned_url)
    return cleaned


def validate_url_syntax(url: str) -> str:
    """
    Validate that the URL is syntactically correct and uses an allowed scheme (http or https).
    Returns the validated URL.
    Raises ValueError with descriptive message if invalid.
    """
    if url.lower().startswith("www."):
        raise ValueError(
            f"URL '{url}' must include an HTTP or HTTPS scheme (e.g. 'https://{url}')."
        )

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL '{url}': {exc}") from exc

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme '{parsed.scheme}' is not supported. Only HTTP and HTTPS URLs are accepted."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL '{url}' is missing a valid domain/host name.")

    labels = hostname.split(".")
    if any(not label for label in labels):
        raise ValueError(f"URL '{url}' contains an invalid host name.")

    if hostname != "localhost" and "." not in hostname:
        raise ValueError(
            f"URL '{url}' domain name must contain a top-level domain (e.g., .com) or be localhost."
        )

    return url


class PostingRequest(BaseModel):
    """Request payload for multi-platform message posting."""

    message: str = Field(
        ...,
        description="Message content to be published. Max 200 characters, containing exactly one CTA URL.",
        examples=[
            "Check out our latest business platform and grow your online visibility. https://example.com"
        ],
    )

    @field_validator("message")
    @classmethod
    def validate_message_and_url(cls, v: str) -> str:
        """Validate character limits and ensure exactly one valid CTA URL exists."""
        # 1. Non-empty / non-whitespace check
        if not v or not v.strip():
            raise ValueError("Message must not be empty.")

        # 2. Maximum character length check
        if len(v) > 200:
            raise ValueError(
                f"Message must not exceed 200 characters (current length: {len(v)})."
            )

        # 3. Exactly one URL check
        urls = extract_urls(v)
        if len(urls) == 0:
            raise ValueError("Message must contain exactly one valid CTA URL.")
        if len(urls) > 1:
            raise ValueError(
                f"Message contains {len(urls)} URLs. Exactly one CTA URL is allowed."
            )

        # 4. URL syntax and scheme validation
        validate_url_syntax(urls[0])

        return v

    @property
    def extracted_url(self) -> str:
        """Extract and return the validated single CTA URL from the message."""
        urls = extract_urls(self.message)
        return urls[0] if urls else ""


class PlatformResult(BaseModel):
    """Result of posting to a single third-party platform."""

    platform: str = Field(..., description="Platform name")
    status: Literal["success", "failed"] = Field(
        ..., description="Posting status ('success' or 'failed')"
    )
    posted_url: Optional[str] = Field(
        default=None, description="Published content URL on the platform"
    )
    public_access: bool = Field(
        default=False, description="Whether the posted content is publicly accessible"
    )
    date: Optional[datetime.date] = Field(
        default=None, description="Posting date in YYYY-MM-DD format"
    )
    time: Optional[datetime.time] = Field(
        default=None, description="Posting time in HH:MM:SS format"
    )
    error: Optional[str] = Field(
        default=None, description="Detailed error description if posting failed"
    )


class PostingResponse(BaseModel):
    """Aggregated response containing results from all target platforms."""

    success: bool = Field(
        ...,
        description="Whether the multi-platform posting operation completed successfully",
    )
    results: List[PlatformResult] = Field(
        default_factory=list,
        description="Individual posting results for each target platform",
    )
