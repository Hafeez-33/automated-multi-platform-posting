# Automated Multi-Platform Posting System

A high-performance, asynchronous multi-platform social media publishing microservice built with **Python 3.12** and **FastAPI**. The system accepts promotional messages (up to 200 characters with a single Call-to-Action link) and broadcasts them concurrently to **Telegram**, **Discord**, **Reddit**, **LinkedIn**, and **Mastodon** via their official REST APIs.

---

## Table of Contents

1. [Problem Statement & Solution](#problem-statement--solution)
2. [Key Features](#key-features)
3. [Supported Platforms](#supported-platforms)
4. [Architecture & Request Flow](#architecture--request-flow)
5. [Technology Stack](#technology-stack)
6. [Project Directory Structure](#project-directory-structure)
7. [Prerequisites](#prerequisites)
8. [Installation Instructions for Windows](#installation-instructions-for-windows)
9. [Virtual Environment Setup](#virtual-environment-setup)
10. [Dependency Installation](#dependency-installation)
11. [Environment Variable Configuration](#environment-variable-configuration)
12. [Instructions to Obtain Platform Credentials](#instructions-to-obtain-platform-credentials)
13. [Running the Application](#running-the-application)
14. [API Endpoint Details](#api-endpoint-details)
15. [Sample Request](#sample-request)
16. [Sample Response](#sample-response)
17. [Input Validation Rules](#input-validation-rules)
18. [Error Handling & Failure Isolation](#error-handling--failure-isolation)
19. [Concurrency Model](#concurrency-model)
20. [Running Automated Tests](#running-automated-tests)
21. [Test Results](#test-results)
22. [Security Considerations](#security-considerations)
23. [Known Limitations](#known-limitations)
24. [Real API Permission Requirements](#real-api-permission-requirements)
25. [Future Improvements](#future-improvements)

---

## Problem Statement & Solution

Marketing campaigns, product updates, and business announcements require consistent, timely distribution across disparate social networks and communication channels. Each platform operates proprietary API endpoints, distinct authentication schemes, differing payload conventions, and unique rate limits:

- **Telegram** requires bot tokens and channel handle targets.
- **Discord** relies on incoming webhooks with query-parameter wait states.
- **Reddit** enforces OAuth 2.0 authorization flows with token refresh operations.
- **LinkedIn** requires dynamic versioned headers, URN author representations, and specific member scopes.
- **Mastodon** distributes statuses across federated, decentralized instance hosts.

Publishing manually or sequentially is error-prone, slow, and causes cumulative latency. 

**Solution**: This system provides a unified REST gateway (`POST /posting`) that parses and strictly validates the promotional message, strips trailing punctuation from URLs, sanitizes sensitive credentials, and dispatches the message concurrently across all five platforms in parallel using non-blocking asynchronous I/O (`asyncio.gather`). If one platform experiences API downtime or authentication failure, other platforms still publish successfully, and the caller receives an aggregated breakdown with partial success reporting.

---

## Key Features

- **Strict Input Validation**: Pydantic v2 enforces a 200-character ceiling, validates domain syntax and HTTP/HTTPS schemes, and verifies the presence of exactly one Call-To-Action (CTA) URL.
- **True Concurrent Publishing**: Executes all five network calls in parallel using Python's `asyncio` and `httpx.AsyncClient`. Total request duration is bounded by the single slowest platform rather than the sequential sum.
- **Complete Failure Isolation**: Two-tier error handling wraps each platform call. Exceptions in one platform adapter never abort or cascade into other adapters.
- **Multi-Tier Credential Sanitization**: Telegram bot tokens, Discord webhook tokens, Reddit refresh/access tokens, LinkedIn access tokens, and Mastodon bearer tokens are automatically scrubbed from error logs and response payloads.
- **Conservative Public Access Auditing**: Accurately reflects whether published content is verified as publicly reachable without user authentication, preventing false public claims on private channels or login-gated feeds.
- **Deterministic Response Ordering**: Results are consistently ordered (`Telegram` &rarr; `Discord` &rarr; `Reddit` &rarr; `LinkedIn` &rarr; `Mastodon`), ensuring stable downstream parsing.
- **Interactive Documentation**: Auto-generated Swagger UI (`/docs`) and ReDoc (`/redoc`) specifications.

---

## Supported Platforms

| Platform | Integration Method | Official API Endpoint | Primary Auth Mechanism | Public Access Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **Telegram** | Bot API | `POST /bot<token>/sendMessage` | Bot Token | `True` for public `@username` channels; `False` otherwise |
| **Discord** | Webhooks API | `POST /api/webhooks/{id}/{token}?wait=true` | Webhook URL / Token | Always `False` (Requires server membership & login) |
| **Reddit** | OAuth2 Data API | `POST /api/submit` | OAuth2 Refresh Token & App Credentials | Always `False` (Login barriers & subreddit filters) |
| **LinkedIn** | Community REST API | `POST /rest/posts` | OAuth2 Bearer Token (`w_member_social`) | Always `False` (Requires authenticated user session) |
| **Mastodon** | Fediverse Status API | `POST {instance}/api/v1/statuses` | Bearer Token (`write:statuses`) | `True` if visibility is `"public"`; `False` otherwise |

---

## Architecture & Request Flow

```
                      +-----------------------------+
                      |         HTTP Client         |
                      |  (POST /posting / Payload)  |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |      FastAPI Router         |
                      |   (Pydantic Validation)     |
                      +--------------+--------------+
                                     |
                       (Valid Message & CTA URL)
                                     v
                      +-----------------------------+
                      |       PostingService        |
                      |  (Dependency Injection)     |
                      +--------------+--------------+
                                     |
                 +-------------------+-------------------+
                 |        asyncio.gather() Concurrency   |
                 +-------------------+-------------------+
                   |         |         |         |         |
                   v         v         v         v         v
               +-------+ +-------+ +-------+ +-------+ +-------+
               |Telegr.| |Discord| |Reddit | |LinkdIn| |Mastod.|
               |Adapter| |Adapter| |Adapter| |Adapter| |Adapter|
               +---+---+ +---+---+ +---+---+ +---+---+ +---+---+
                   |         |         |         |         |
    (HTTPX Async)  |         |         |         |         |
                   v         v         v         v         v
               [Telegram [Discord   [Reddit   [LinkedIn [Mastodon
                 Cloud]    Cloud]    Cloud]    Cloud]    Cloud]
                   |         |         |         |         |
                   +---------+----+----+---------+---------+
                                  |
                                  v
                      +-----------------------------+
                      | Deterministic Aggregator    |
                      |  - Error Sanitization       |
                      |  - PlatformResult Mapping   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |  HTTP 200 PostingResponse   |
                      |  (success: bool, results[]) |
                      +-----------------------------+
```

---

## Technology Stack

- **Runtime**: Python 3.12 (64-bit)
- **Web Framework**: [FastAPI](https://fastapi.tiangolo.com/) (v0.115+)
- **ASGI Server**: [Uvicorn](https://www.uvicorn.org/) (Standard async server)
- **Data Serialization & Validation**: [Pydantic v2](https://docs.pydantic.dev/latest/)
- **Configuration Management**: [Pydantic-Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) & `python-dotenv`
- **Asynchronous HTTP Client**: [HTTPX](https://www.python-httpx.org/)
- **Testing Framework**: [Pytest](https://docs.pytest.org/) & [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- **Mocking Utilities**: `unittest.mock` & [respx](https://lundberg.github.io/respx/)

---

## Project Directory Structure

```
automated-multi-platform-posting/
├── app/
│   ├── __init__.py              # Package initializer
│   ├── main.py                  # FastAPI application setup, routes & dependencies
│   ├── config.py                # Pydantic BaseSettings environment loader
│   ├── schemas.py               # Pydantic v2 request & response models
│   ├── platforms/               # Platform adapter implementations
│   │   ├── __init__.py          # Platform package exports
│   │   ├── base.py              # BasePlatform abstract base class (ABC)
│   │   ├── telegram.py          # Telegram Bot API implementation
│   │   ├── discord.py           # Discord Webhook API implementation
│   │   ├── reddit.py            # Reddit OAuth2 authorization & submission adapter
│   │   ├── linkedin.py          # LinkedIn REST Posts API adapter
│   │   └── mastodon.py          # Mastodon Fediverse Status API adapter
│   └── services/                # Business logic and orchestrators
│       ├── __init__.py          # Services package exports
│       └── posting_service.py   # Multi-platform async orchestrator & sanitization
├── docs/
│   └── platform-api-research.md # Official API documentation and authentication research
├── tests/
│   ├── __init__.py              # Test suite package
│   └── test_posting.py          # Complete unit, integration, and E2E test suite (126 tests)
├── .env.example                 # Template for required environment variables
├── .gitignore                   # Excludes venv, .env, __pycache__, and temporary logs
├── pytest.ini                   # Pytest configuration and asyncio loop settings
├── requirements.txt             # Locked project dependencies
└── README.md                    # Project documentation
```

---

## Prerequisites

- **Operating System**: Windows 10/11 (or Linux/macOS)
- **Python**: Version 3.12 or newer
- **Git**: Installed and available in your system path
- **Terminal**: Windows PowerShell or Command Prompt

Verify Python 3.12 installation:
```powershell
py -3.12 --version
# Output: Python 3.12.x
```

---

## Installation Instructions for Windows

Clone the repository to your local machine:
```powershell
git clone https://github.com/Hafeez-33/automated-multi-platform-posting.git
cd automated-multi-platform-posting
```

---

## Virtual Environment Setup

Create and activate an isolated Python 3.12 virtual environment:

### In PowerShell:
```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### In Command Prompt (cmd.exe):
```cmd
py -3.12 -m venv venv
.\venv\Scripts\activate.bat
```

---

## Dependency Installation

Upgrade `pip` and install all required runtime and testing dependencies:
```powershell
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\pip.exe install -r requirements.txt
```

---

## Environment Variable Configuration

Create your local `.env` configuration file from the provided `.env.example` template:

```powershell
Copy-Item .env.example .env
```

Open `.env` in your text editor and configure the credentials for each target platform:

```env
# Application Settings
APP_NAME="Automated Multi-Platform Posting System"
APP_ENV="development"
PORT=4000
HOST="0.0.0.0"

# 1. Telegram
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
TELEGRAM_CHAT_ID="@your_public_channel_username"

# 2. Discord
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/your_webhook_id/your_webhook_token"

# 3. Reddit
REDDIT_CLIENT_ID="your_reddit_client_id"
REDDIT_CLIENT_SECRET="your_reddit_client_secret"
REDDIT_REFRESH_TOKEN="your_reddit_refresh_token"
REDDIT_ACCESS_TOKEN=""
REDDIT_USER_AGENT="AutomatedPoster/1.0.0"
REDDIT_SUBREDDIT="test"

# 4. LinkedIn
LINKEDIN_ACCESS_TOKEN="your_linkedin_access_token"
LINKEDIN_AUTHOR_URN="urn:li:person:your_person_id"
LINKEDIN_VERSION="202611"

# 5. Mastodon
MASTODON_INSTANCE_URL="https://mastodon.social"
MASTODON_ACCESS_TOKEN="your_mastodon_access_token"
```

> **Note**: If a platform is not configured in `.env`, the system safely catches the missing credentials and marks that platform result as `failed` with a clear explanation, without failing the overall request or terminating other platforms.

---

## Instructions to Obtain Platform Credentials

### 1. Telegram (Bot API)
1. Open Telegram and search for the official `@BotFather`.
2. Send `/newbot`, enter a display name and unique username ending in `bot`.
3. Copy the generated HTTP API **Bot Token** (format: `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
4. Create a public channel, navigate to Channel Settings &rarr; Administrators &rarr; **Add Administrator**, and add your bot with "Post Messages" permission.
5. Set `TELEGRAM_CHAT_ID="@your_channel_handle"`.

### 2. Discord (Webhooks API)
1. Open your Discord server and navigate to your target text channel.
2. Click **Edit Channel** (gear icon) &rarr; **Integrations** &rarr; **Webhooks**.
3. Click **New Webhook**, assign a name, and choose the destination channel.
4. Click **Copy Webhook URL** and set `DISCORD_WEBHOOK_URL`.

### 3. Reddit (OAuth2 Data API)
1. Log in to [Reddit App Preferences](https://www.reddit.com/prefs/apps).
2. Click **create another app...** at the bottom of the page.
3. Select the **script** app type.
4. Set name and redirect URI (e.g. `http://localhost:8080`).
5. Copy the **Client ID** (under the app name) and the **Client Secret**.
6. Generate an OAuth2 **Refresh Token** via an OAuth script or postman flow with the `submit` and `identity` scopes.
7. Configure `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_REFRESH_TOKEN`.
8. *Note: Plaintext username/password authentication is strictly disallowed.*

### 4. LinkedIn (REST Posts API)
1. Log in to the [LinkedIn Developer Portal](https://www.linkedin.com/developers/).
2. Create an Application and link it to your verified LinkedIn Page or personal profile.
3. In the "Products" tab, request access to **Share on LinkedIn** and **Sign In with LinkedIn using OpenID Connect**.
4. Generate an OAuth 2.0 user access token with the `w_member_social` (for personal profiles) or `w_organization_social` scope.
5. Retrieve your author URN (format: `urn:li:person:abcdef1234` or `urn:li:organization:12345678`).
6. Configure `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN`, and set `LINKEDIN_VERSION="202611"`.

### 5. Mastodon (Fediverse Status API)
1. Log in to your Mastodon instance account (e.g., `https://mastodon.social`).
2. Navigate to **Preferences** &rarr; **Development** &rarr; **New Application**.
3. Name your application and grant the **`write:statuses`** permission scope.
4. Submit the form, open the application details, and copy your **Access Token**.
5. Set `MASTODON_INSTANCE_URL` to your instance base URL (e.g., `https://mastodon.social`) and set `MASTODON_ACCESS_TOKEN`.

---

## Running the Application

Start the FastAPI application with Uvicorn:

```powershell
.\venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 4000 --reload
```

Output:
```
INFO:     Uvicorn running on http://0.0.0.0:4000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Application startup complete.
```

The application is now live on port 4000:
- **Root Health Check**: `http://localhost:4000/`
- **Interactive API Docs (Swagger UI)**: `http://localhost:4000/docs`
- **Alternative Docs (ReDoc)**: `http://localhost:4000/redoc`
- **Publishing Endpoint**: `http://localhost:4000/posting`

---

## API Endpoint Details

### 1. `GET /` — Health Check
Returns service health and active configuration metadata.
- **Method**: `GET`
- **Response**: `200 OK`
```json
{
  "status": "healthy",
  "app": "Automated Multi-Platform Posting System",
  "environment": "development",
  "docs": "/docs"
}
```

### 2. `POST /posting` — Multi-Platform Publishing
Publishes a validated message and CTA URL across all five platforms concurrently.
- **Method**: `POST`
- **Content-Type**: `application/json`
- **Status Codes**:
  - `200 OK`: Message validated; publishing completed (even if individual platforms encountered API errors).
  - `422 Unprocessable Entity`: Input validation failure (e.g. message > 200 chars, zero URLs, multiple URLs, invalid host).

---

## Sample Request

```bash
curl -X POST "http://localhost:4000/posting" \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Check out our latest business platform and grow your online visibility. https://example.com"
     }'
```

---

## Sample Response

```json
{
  "success": true,
  "results": [
    {
      "platform": "Telegram",
      "status": "success",
      "posted_url": "https://t.me/your_public_channel_username/101",
      "public_access": true,
      "date": "2026-11-18",
      "time": "21:30:00",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "success",
      "posted_url": "https://discord.com/channels/123456789012345678/987654321098765432/112233445566778899",
      "public_access": false,
      "date": "2026-11-18",
      "time": "21:30:01",
      "error": null
    },
    {
      "platform": "Reddit",
      "status": "success",
      "posted_url": "https://www.reddit.com/r/test/comments/abc123/check_out_our_latest_business_platform/",
      "public_access": false,
      "date": "2026-11-18",
      "time": "21:30:01",
      "error": null
    },
    {
      "platform": "LinkedIn",
      "status": "success",
      "posted_url": "https://www.linkedin.com/feed/update/urn:li:share:1234567890",
      "public_access": false,
      "date": "2026-11-18",
      "time": "21:30:02",
      "error": null
    },
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@exampleuser/112233445566778899",
      "public_access": true,
      "date": "2026-11-18",
      "time": "21:30:00",
      "error": null
    }
  ]
}
```

---

## Input Validation Rules

The `PostingRequest` schema enforces strict checks before any platform adapter is called:

1. **Character Length**: `len(message) <= 200`. Payloads exceeding 200 characters are rejected with HTTP 422.
2. **Non-Empty Content**: Empty strings or whitespace-only messages raise a validation error.
3. **Single CTA URL Constraint**: The message must contain **exactly one** valid CTA URL. Zero URLs or multiple URLs trigger HTTP 422.
4. **Supported Scheme**: Only `http://` and `https://` protocols are permitted. Unsupported schemes (`ftp://`, `file://`, `mailto:`) are rejected.
5. **Scheme Enforcement**: URLs beginning with `www.` must include an explicit scheme (e.g. `https://www.example.com`).
6. **Domain Syntax**: Validates that domain labels are non-empty and possess a valid top-level domain (TLD) or resolve to `localhost`.
7. **Punctuation Stripping**: Automatically cleans attached trailing sentence punctuation (e.g., `https://example.com.` or `(https://example.com)`) to preserve clean URLs.

---

## Error Handling & Failure Isolation

The application employs a defense-in-depth failure isolation strategy:

1. **Adapter-Level Isolation**: Each platform adapter catches its own network timeouts, HTTP errors, and JSON decode failures, converting exceptions into a `PlatformResult(status="failed", error="...")`.
2. **Orchestrator-Level Isolation**: `PostingService._safe_publish()` wraps each platform execution in a safety handler, verifying returned object types and platform names.
3. **Async Exception Boundary**: `asyncio.gather(*tasks, return_exceptions=True)` guarantees that an unhandled crash or exception in one platform cannot terminate or interrupt other in-flight requests.
4. **Deterministic Aggregation**: If any platform fails, the overall response returns `success: false` while returning HTTP 200 with complete diagnostic results for every platform.
5. **Credential Scrubbing**: `_sanitize_error_text()` scrubs tokens, secrets, and authorization headers from error strings before returning them in the response.

---

## Concurrency Model

Rather than executing platform API calls sequentially (which would accumulate latencies of 500ms + 400ms + 600ms + 800ms + 300ms &approx; 2.6 seconds), `PostingService` leverages Python's native asynchronous event loop:

- All five platform tasks are dispatched concurrently via `asyncio.gather()`.
- HTTP I/O is non-blocking via `httpx.AsyncClient`.
- Total wall-clock time is bounded by the slowest single network roundtrip (e.g. &approx; 800ms).
- Response ordering is deterministically sorted to prevent race-condition instability in client consumers.

---

## Running Automated Tests

Run the complete test suite using pytest:

```powershell
.\venv\Scripts\pytest -v
```

To run with coverage reporting:
```powershell
.\venv\Scripts\pytest -v --cov=app --cov-report=term-missing
```

> **Important Note on Testing Methodology**:
> The automated test suite utilizes mocked HTTP requests (`respx` and `unittest.mock`) to verify behavior across all status codes, error paths, and edge cases. **No live third-party network calls are made during automated test execution.** This ensures fast, repeatable tests without creating spam, hitting rate limits, or leaking API tokens.

---

## Test Results

The test suite validates:
- Request schema validation (empty messages, character limits, multiple URLs, invalid schemes).
- Base platform inheritance and interface contracts.
- Platform configuration and fallback behavior.
- Telegram, Discord, Reddit, LinkedIn, and Mastodon adapter success and failure paths.
- Asynchronous orchestration, deterministic ordering, and complete failure isolation.
- Credential scrubbing and security token redaction across all error pathways.

```
============================= test session starts =============================
platform win32 -- Python 3.12.9, pytest-9.2.0, pluggy-1.7.0
rootdir: D:\A PROJECT\Dxora Assignement
configfile: pytest.ini
plugins: anyio-4.16.0, asyncio-1.5.0
collected 126 items

tests/test_posting.py ................................................... [ 40%]
tests/test_posting.py ................................................... [ 80%]
tests/test_posting.py ..........................                          [100%]

======================= 126 passed, 1 warning in 24.60s =======================
```

---

## Security Considerations

1. **Credential Segregation**: Secrets are managed exclusively via environment variables and `.env`. The `.env` file is excluded from version control via `.gitignore`.
2. **No Plaintext Passwords**: Reddit username/password authentication is excluded; only standard OAuth 2.0 authorization code / refresh tokens are supported.
3. **Zero Credential Leakage**: Error handling includes an active scrubbing filter that redacts Telegram bot tokens, Discord webhook secrets, Reddit client secrets/refresh tokens, LinkedIn bearer tokens, and Mastodon bearer tokens.
4. **Non-Root Execution**: Container setups or production processes should run under a dedicated, unprivileged system user.
5. **No Local Echo**: Access tokens obtained during Reddit token refresh flows are sanitized and never reflected in responses or application logs.

---

## Known Limitations

1. **Text & Link Only**: Current implementation is tailored for text and link promotions; direct media uploads (images, videos, PDF attachments) are out of scope for this stage.
2. **Token Lifespans**: LinkedIn OAuth access tokens expire every 60 days and must be re-issued by an administrator.
3. **Public Access Constraints**: Reddit and LinkedIn enforce platform-wide authentication walls or community membership gates. Consequently, `public_access` for these platforms is conservatively marked as `False`.
4. **Third-Party Rate Limits**: High-frequency bulk publishing must account for platform rate limits (e.g. Telegram 30 msg/sec, Discord 5 requests/sec per webhook, Reddit 60 req/min).

---

## Real API Permission Requirements

To publish live content to third-party platforms in production, ensure your accounts possess the following privileges:

- **Telegram**: The bot must be added as an **Administrator** in the public channel with the `can_post_messages` permission enabled.
- **Discord**: The webhook must be created inside an active text channel where the user has `Manage Webhooks` authority.
- **Reddit**: The Reddit account must have sufficient karma/account age to post in target subreddits without being caught by AutoModerator filters, and the registered script app must have the `submit` OAuth scope.
- **LinkedIn**: The LinkedIn app must have verified company/profile association and granted the `w_member_social` or `w_organization_social` scope.
- **Mastodon**: The application token must be granted the `write:statuses` scope on the target instance.

---

## Future Improvements

- **Interactive OAuth Web Interface**: Built-in OAuth 2.0 PKCE flow UI for one-click generation and refreshing of LinkedIn and Reddit tokens.
- **Media Upload Pipeline**: Support for image, banner, and video attachments via multi-part upload handlers.
- **Distributed Task Queue**: Offloading publishing to Celery or Redis RQ with exponential backoff and automated retry jitter.
- **Database Audit Log**: Persistent storage (PostgreSQL/SQLAlchemy) to record historical publication statuses, timestamps, and response payloads.
- **Webhook Delivery Notifications**: Outbound webhooks to notify client systems when background publishing jobs complete.
