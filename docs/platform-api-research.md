# Official Platform API Research & Integration Specifications

This document contains verified technical research from official documentation for all five target platforms integrated into the **Automated Multi-Platform Posting System**:

1. **Telegram** (Bot API)
2. **Discord** (Execute Webhook API)
3. **Reddit** (Data API / OAuth2 Submissions)
4. **LinkedIn** (REST Posts API)
5. **Mastodon** (Decentralized Fediverse Status API)

---

## 1. Telegram Bot API

### Official Documentation
- **Official API Documentation**: [https://core.telegram.org/bots/api](https://core.telegram.org/bots/api)
- **`sendMessage` Method Reference**: [https://core.telegram.org/bots/api#sendmessage](https://core.telegram.org/bots/api#sendmessage)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage`
- **Content-Type**: `application/json`

### Authentication Method
- Token-based URL path authentication. The bot token issued by `@BotFather` is passed in the URL path (`/bot<token>/`).

### Required Permissions & Channel Setup
- The bot must be added to the target channel as an **Administrator**.
- Required administrative right: `can_post_messages: true`.

### Request Payload Format
```json
{
  "chat_id": "@your_public_channel_username",
  "text": "Check out our latest business platform and grow your online visibility. https://example.com",
  "disable_web_page_preview": false
}
```

### Success Response Structure
HTTP `200 OK` with JSON:
```json
{
  "ok": true,
  "result": {
    "message_id": 12345,
    "sender_chat": {
      "id": -1001234567890,
      "title": "Dxora Public Channel",
      "username": "dxora_public_channel",
      "type": "channel"
    },
    "chat": {
      "id": -1001234567890,
      "title": "Dxora Public Channel",
      "username": "dxora_public_channel",
      "type": "channel"
    },
    "date": 1731931200,
    "text": "Check out our latest business platform and grow your online visibility. https://example.com"
  }
}
```

### Published URL & Public Access Evaluation
- **Published URL**:
  - For public channels with an `@username`: `https://t.me/<username>/<message_id>` (e.g. `https://t.me/dxora_public_channel/12345`).
  - For private channels without an `@username`: Telegram constructs an internal web link formatted as `https://t.me/c/<clean_chat_id>/<message_id>` (where `clean_chat_id` is the numeric chat ID without the `-100` prefix).
- **Public Access Determination**:
  - `public_access = True`: **Only** if the target chat is a public channel with a public handle (`chat_id` begins with `@` or `chat.username` is present in the response). These channels have public web previews viewable anonymously in any browser.
  - `public_access = False`: If the channel is private, or if the chat is a group or direct message. These require an invite link and active Telegram account login; anonymous web access is rejected.

### Rate Limits & Platform Limitations
- **Rate Limits**: Maximum 30 messages per second across all chats; maximum 20 messages per minute to the same channel or group.
- **Payload Constraint**: Up to 4,096 characters per text message.

---

## 2. Discord Webhook API

### Official Documentation
- **Official Webhook Documentation**: [https://discord.com/developers/docs/resources/webhook](https://discord.com/developers/docs/resources/webhook)
- **Execute Webhook Reference**: [https://discord.com/developers/docs/resources/webhook#execute-webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://discord.com/api/v10/webhooks/{webhook.id}/{webhook.token}?wait=true`
- **Content-Type**: `application/json`

> **Critical Parameter `?wait=true`**:
> By default, the Discord Webhook execution endpoint returns `204 No Content` with an empty body. Appending query parameter `?wait=true` forces Discord to wait for message processing and return HTTP `200 OK` with the complete Message object, which is required to obtain the message ID.

### Authentication Method
- Webhook token embedded in the URL path (`/webhooks/{webhook.id}/{webhook.token}`). No separate `Authorization` header is required.

### Required Permissions & Channel Setup
- Requires a webhook created in a text channel on a Discord server where the user or bot has `Manage Webhooks` permissions.

### Request Payload Format
```json
{
  "content": "Check out our latest business platform and grow your online visibility. https://example.com"
}
```

### Success Response Structure
HTTP `200 OK` (when `wait=true` is appended):
```json
{
  "id": "1307682949281726514",
  "type": 0,
  "content": "Check out our latest business platform and grow your online visibility. https://example.com",
  "channel_id": "1199382103982910291",
  "guild_id": "1199382000000000000",
  "author": {
    "bot": true,
    "id": "1307682949281726510",
    "username": "Dxora Poster",
    "avatar": null,
    "discriminator": "0000"
  },
  "attachments": [],
  "embeds": [],
  "timestamp": "2026-11-18T12:00:00.000000+00:00",
  "webhook_id": "1307682949281726510"
}
```

### Published URL & Public Access Evaluation
- **Published URL**:
  - If `guild_id` is present: `https://discord.com/channels/{guild_id}/{channel_id}/{message_id}`
  - If `guild_id` is omitted: `https://discord.com/channels/@me/{channel_id}/{message_id}`
- **Public Access Determination**:
  - `public_access = False`: Discord channels are enclosed within server boundaries requiring user authentication and guild member permissions. An unauthenticated web user navigating to the URL cannot view the content.

### Rate Limits & Platform Limitations
- **Rate Limits**: 5 requests per 2 seconds per webhook route. Responses return standard Discord rate-limit headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`, and `Retry-After`.
- **Payload Constraint**: Maximum 2,000 characters per message.

---

## 3. Reddit Data API

### Official Documentation
- **Official API Documentation**: [https://www.reddit.com/dev/api](https://www.reddit.com/dev/api)
- **Submit Endpoint Reference**: [https://www.reddit.com/dev/api#POST_api_submit](https://www.reddit.com/dev/api#POST_api_submit)
- **Reddit Data API Terms & Guidelines**: [https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- **Reddit OAuth2 Specifications**: [https://github.com/reddit-archive/reddit/wiki/OAuth2](https://github.com/reddit-archive/reddit/wiki/OAuth2)

### Reassessment of Password-Grant Authentication
- **Security Vulnerability**: The legacy OAuth2 Resource Owner Password Credentials (ROPC / password grant) requires storing the user's plaintext Reddit password in environment variables (`.env`). This violates modern security standards and is formally deprecated in OAuth 2.1.
- **Account Vulnerability**: Any Reddit account with Two-Factor Authentication (2FA) enabled will reject password-grant authentication.
- **Current Official Policy**: Reddit strongly discourages password-based authentication for modern applications and requires developers to comply with the updated Reddit Developer Terms.
- **Recommended OAuth Flow**:
  1. **OAuth 2.0 Authorization Code Flow with Refresh Token**:
     - The developer or user authorizes the app once via browser to obtain an authorization code.
     - The app exchanges the code for a persistent `refresh_token` with scopes `submit` and `identity`.
     - At runtime, the application requests short-lived access tokens via `grant_type=refresh_token` using `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, and `REDDIT_REFRESH_TOKEN`.
     - **No user password is ever stored or transmitted.**
  2. **Backward-Compatible Script Grant (Legacy Fallback Only)**:
     - If a developer strictly runs a personal script application registered under their own profile, Reddit's `grant_type=password` remains functional for legacy non-2FA script apps, but it should be treated as a legacy fallback, not a modern best practice.

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://oauth.reddit.com/api/submit`
- **Headers**:
  - `Authorization: Bearer <access_token>`
  - `User-Agent: <REDDIT_USER_AGENT>` (e.g., `DxoraPoster/1.0.0 (by /u/<developer_username>)` — Reddit strictly requires descriptive, non-generic User-Agents).
  - `Content-Type: application/x-www-form-urlencoded`

### Required Permissions & Approval Prerequisites
- **Registration**: Registered client application at `https://www.reddit.com/prefs/apps`.
- **Developer Terms**: Acceptance of Reddit Data API Terms of Use.
- **OAuth Scopes**: `submit` (to submit posts) and `identity` (to verify account identity).
- **Subreddit Requirements**:
  - Target subreddit must permit self/text posts (e.g. `r/test` or the user's profile subreddit `r/u_<username>`).
  - Posting accounts must meet karma and account age thresholds enforced by subreddit AutoModerator rules.

### Request Payload Format
Form URL-encoded (`application/x-www-form-urlencoded`):
```text
api_type=json&sr=test&kind=self&title=Online%20Platform%20Announcement&text=Check%20out%20our%20latest%20business%20platform%20and%20grow%20your%20online%20visibility.%20https%3A%2F%2Fexample.com&send_replies=true
```

### Success Response Structure
HTTP `200 OK` with JSON:
```json
{
  "json": {
    "errors": [],
    "data": {
      "url": "https://www.reddit.com/r/test/comments/1gxabc/online_platform_announcement/",
      "drafts_count": 0,
      "id": "1gxabc",
      "name": "t3_1gxabc"
    }
  }
}
```

### Published URL & Public Access Evaluation
- **Published URL**: Returned directly by the Reddit API in `response["json"]["data"]["url"]`.
- **Public Access Determination**:
  - `public_access = True`: When posted to a public subreddit (such as `r/test`) and not flagged or quarantined.
  - `public_access = False`: If posted to a private subreddit, or if caught in an automated spam queue / removed by AutoModerator (where external visitors only see `[removed]`).

### Official Rate Limits
- **OAuth-Authenticated Requests**: **100 queries per minute (QPM)** per registered client ID, calculated as an average over a rolling 10-minute window (approximately 1,000 requests per 10 minutes).
- **Non-OAuth Requests**: **10 queries per minute (QPM)** (strictly throttled or blocked).
- **Quota Tracking Headers**:
  - `X-Ratelimit-Used`: Number of requests consumed in the current window.
  - `X-Ratelimit-Remaining`: Number of requests remaining.
  - `X-Ratelimit-Reset`: Seconds remaining until quota reset.

---

## 4. LinkedIn REST Posts API

### Official Documentation
- **Official Consumer Integrations**: [https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin)
- **Community Management Posts API**: [https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
- **LinkedIn API Versioning & Lifespan Policy**: [https://learn.microsoft.com/en-us/linkedin/marketing/versioning](https://learn.microsoft.com/en-us/linkedin/marketing/versioning)

### API Versioning & Header Requirements
- **Dynamic Version Header (`Linkedin-Version`)**:
  - LinkedIn enforces monthly API versioning in the format: `YYYYMM` (e.g. `202411`, `202501`).
  - **Deprecation Lifecycle**: Marketing API versions have a minimum supported lifespan of **1 year** from release before sunset. Older versions (such as `202401`) are permanently retired, causing requests to fail.
  - **Architectural Requirement**: The API version must **never be hardcoded**. It must be configurable via an application setting or environment variable (`LINKEDIN_VERSION`) to allow painless monthly or annual migrations without code refactoring.
- **Protocol Version Header**: `X-Restli-Protocol-Version: 2.0.0` is required for all LinkedIn Rest.li endpoints.

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://api.linkedin.com/rest/posts`
- **Headers**:
  - `Authorization: Bearer <LINKEDIN_ACCESS_TOKEN>`
  - `Linkedin-Version: <LINKEDIN_VERSION>` (e.g., active supported `YYYYMM`)
  - `X-Restli-Protocol-Version: 2.0.0`
  - `Content-Type: application/json`

### Required Permissions & App Approval
- **Scopes**:
  - `w_member_social`: For publishing posts on behalf of an authenticated individual member.
  - `w_organization_social`: For publishing posts on behalf of an authenticated LinkedIn Page / Organization.
- **Product Approval**: The developer app on the [LinkedIn Developer Portal](https://www.developer.linkedin.com/) must have the "Share on LinkedIn" or "Community Management API" product approved and active.

### Request Payload Format
```json
{
  "author": "urn:li:person:YOUR_PERSON_ID",
  "commentary": "Check out our latest business platform and grow your online visibility. https://example.com",
  "visibility": "PUBLIC",
  "distribution": {
    "feedDistribution": "MAIN_FEED",
    "targetEntities": [],
    "thirdPartyDistributionChannels": []
  },
  "lifecycleState": "PUBLISHED",
  "isReshareDisabledByAuthor": false
}
```

### Success Response & Post URN Retrieval
- **Status Code**: HTTP `201 Created`
- **Entity ID**: Returned in the response header **`x-restli-id`** (e.g., `urn:li:share:7123456789012345678`).
- **Body**: Minimal JSON or empty body.

### Published URL & Public Access Evaluation
- **Published URL (Unverified Client Convention)**:
  - The official LinkedIn REST Posts API does **not** provide a canonical browser URL field in its response body or headers.
  - Developers conventionally construct the feed link as:
    `https://www.linkedin.com/feed/update/{x-restli-id}/`
  - **Verification Status: UNRESOLVED / REQUIRING VERIFICATION**: This URL format is a web client convention. It must be verified against active LinkedIn routing for both person (`urn:li:share:...`) and organization author URNs.
- **Public Access Determination**:
  - `public_access`: While the payload specifies `"visibility": "PUBLIC"`, LinkedIn actively gates public feed content behind an authentication wall or login interstitial for unauthenticated desktop and mobile visitors. Therefore, `public_access` cannot be guaranteed without empirical validation of guest access policies.

### Rate Limits & Platform Limitations
- **Rate Limits**: 100 posts per user per day; 250 requests per minute application-wide.
- **Token Lifespan**: Member OAuth access tokens expire in 60 days and must be refreshed.

---

## 5. Mastodon API

### Official Documentation
- **Official Methods Documentation**: [https://docs.joinmastodon.org/methods/statuses/](https://docs.joinmastodon.org/methods/statuses/)
- **Create Status Reference**: [https://docs.joinmastodon.org/methods/statuses/#create](https://docs.joinmastodon.org/methods/statuses/#create)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://<MASTODON_INSTANCE_URL>/api/v1/statuses` (e.g. `https://mastodon.social/api/v1/statuses`)
- **Headers**:
  - `Authorization: Bearer <MASTODON_ACCESS_TOKEN>`
  - `Content-Type: application/json`

### Required Permissions & Scopes
- Scope: `write:statuses` (issued via instance user settings under `Preferences -> Development -> New Application`).

### Request Payload Format
```json
{
  "status": "Check out our latest business platform and grow your online visibility. https://example.com",
  "visibility": "public"
}
```

### Success Response Structure
HTTP `200 OK` with JSON Status Object:
```json
{
  "id": "113504829104829104",
  "created_at": "2026-11-18T12:00:00.000Z",
  "visibility": "public",
  "uri": "https://mastodon.social/users/dxora/statuses/113504829104829104",
  "url": "https://mastodon.social/@dxora/113504829104829104",
  "content": "<p>Check out our latest business platform and grow your online visibility. <a href=\"https://example.com\" target=\"_blank\">https://example.com</a></p>",
  "account": {
    "id": "1098234",
    "username": "dxora",
    "url": "https://mastodon.social/@dxora"
  }
}
```

### Published URL & Public Access Evaluation
- **Published URL**: Returned directly by the Mastodon API in `response["url"]` (e.g., `https://mastodon.social/@dxora/113504829104829104`).
- **Public Access Determination**:
  - `public_access = True`: When `visibility` is `"public"` or `"unlisted"`. These statuses are served directly over public web pages without requiring a login.
  - `public_access = False`: When `visibility` is `"private"` (followers only) or `"direct"` (direct message), as unauthenticated visitors cannot view them.

### Rate Limits & Platform Limitations
- **Rate Limits**: 300 requests per 5 minutes per user account (standard Mastodon rate limit, verified via `X-RateLimit-*` response headers).
- **Federation**: Works across any standard Mastodon or compatible Fediverse instance.

---

## 6. Public Access Evaluation Matrix

A successful API response (HTTP 200 or 201) does **not** automatically mean the post is publicly accessible on the open internet without login. The following matrix governs how `public_access` must be determined:

| Platform | Success HTTP Status | Official Published URL Source | `public_access` Value | Justification & Verification Criteria |
| :--- | :--- | :--- | :--- | :--- |
| **Telegram** | `200 OK` | Inferred (`t.me/<username>/<id>`) | `True` (Public Channel) / `False` (Private Channel/Group) | Verified via chat type: only public channels (`@channel_username`) provide web previews accessible without an account. |
| **Discord** | `200 OK` (with `wait=true`) | Inferred (`discord.com/channels/...`) | `False` | Discord channels are closed walled gardens; anonymous access is blocked by the Discord client gateway. |
| **Reddit** | `200 OK` | Official field (`json.data.url`) | `True` (Public Subreddit) / `False` (Spam-filtered / Private) | Public subreddits allow unauthenticated browser viewing, unless flagged by spam filters or AutoModerator. |
| **LinkedIn** | `201 Created` | Inferred from `x-restli-id` header | **Unresolved / Inferred** (Requires Verification) | Although flagged `PUBLIC`, LinkedIn often presents a login wall to unauthenticated visitors; canonical web URL is not provided in REST body. |
| **Mastodon** | `200 OK` | Official field (`url`) | `True` (Public / Unlisted) / `False` (Private / Direct) | When posted with `visibility: "public"`, the web permalink is publicly accessible without login. |

---

## 7. Unresolved Items & Verification Requirements for Stage 4

Before implementing the platform adapters in Stage 4, the following items must be verified:

1. **LinkedIn Canonical URL**:
   - Verify whether `https://www.linkedin.com/feed/update/{x-restli-id}/` is universally navigable without authentication or if a secondary share inspection endpoint is required.
2. **Reddit Token Configuration**:
   - Provide support for `REDDIT_REFRESH_TOKEN` or direct `REDDIT_ACCESS_TOKEN` in configuration to avoid storing raw Reddit passwords, while retaining backward compatibility if legacy script credentials are used.
3. **LinkedIn Version Configuration**:
   - Ensure `LINKEDIN_VERSION` is exposed in `app/config.py` with an active supported default (e.g. `202411` or dynamic current `YYYYMM`).
4. **Telegram Chat Type Detection**:
   - Adapter logic must inspect the configured `chat_id`: if it begins with `@`, mark `public_access = True`; if numeric (e.g. `-100...`), mark `public_access = False`.
5. **Discord Guild Identification**:
   - If the webhook response object omits `guild_id`, format the message URL cleanly using `https://discord.com/channels/@me/{channel_id}/{message_id}`.
