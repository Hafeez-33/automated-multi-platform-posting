# Official Platform API Research & Integration Specifications

This document contains in-depth research of the official REST API documentation for all five target platforms integrated into the **Automated Multi-Platform Posting System**:

1. **Telegram** (Bot API)
2. **Discord** (Execute Webhook API)
3. **Reddit** (OAuth2 Submissions API)
4. **LinkedIn** (Consumer / Community Posts API)
5. **Mastodon** (Decentralized Fediverse Status API)

---

## 1. Telegram Bot API

### Official Documentation
- **Official Docs**: [https://core.telegram.org/bots/api](https://core.telegram.org/bots/api)
- **Method Reference**: [https://core.telegram.org/bots/api#sendmessage](https://core.telegram.org/bots/api#sendmessage)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage`
- **Content-Type**: `application/json`

### Authentication Method
- **Authentication**: Token-based URL path authentication. The bot token obtained from `@BotFather` is embedded directly into the request URL path (`/bot<token>/`).

### Required Permissions & Scopes
- Bot must be added to the target channel or group as an **Administrator**.
- Channel permission required: `Post Messages` (`can_post_messages: true`).

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
      "title": "My Public Channel",
      "username": "my_public_channel",
      "type": "channel"
    },
    "chat": {
      "id": -1001234567890,
      "title": "My Public Channel",
      "username": "my_public_channel",
      "type": "channel"
    },
    "date": 1731931200,
    "text": "Check out our latest business platform and grow your online visibility. https://example.com"
  }
}
```

### Post URL Construction & Public Access
- **Public Access**: `True` if posting to a public channel with a username (`@channel_username`).
- **URL Pattern**: `https://t.me/<channel_username>/<message_id>`
  - Example: `https://t.me/my_public_channel/12345`
  - For private channels without a public username: `https://t.me/c/<clean_chat_id>/<message_id>` (where `clean_chat_id` removes the `-100` prefix). Note: Private channels require membership to view.

### Rate Limits & Platform Limitations
- **Rate Limit**: Maximum 30 messages per second across all chats; maximum 20 messages per minute to the same group/channel.
- **Message Length**: Up to 4,096 characters (our constraint is 200 chars, well within limit).
- **Prerequisites**: A bot created via `@BotFather`, a public or private channel, and the bot granted admin rights.

---

## 2. Discord Webhook API

### Official Documentation
- **Official Docs**: [https://discord.com/developers/docs/resources/webhook](https://discord.com/developers/docs/resources/webhook)
- **Execute Webhook Reference**: [https://discord.com/developers/docs/resources/webhook#execute-webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://discord.com/api/v10/webhooks/{webhook.id}/{webhook.token}?wait=true`
- **Content-Type**: `application/json`

> **Critical Parameter: `?wait=true`**:
> By default, Discord Webhooks return `204 No Content` without a response body. Appending `?wait=true` instructs Discord to wait for message delivery and return `200 OK` with the complete Message object containing `id`, `channel_id`, and `guild_id`.

### Authentication Method
- **Authentication**: Webhook token embedded in the URL path (`{webhook.id}/{webhook.token}`). No separate `Authorization` header is needed.

### Required Permissions & Scopes
- Webhook must be created in a Discord text channel by an administrator or member with `Manage Webhooks` permissions.

### Request Payload Format
```json
{
  "content": "Check out our latest business platform and grow your online visibility. https://example.com"
}
```

### Success Response Structure
HTTP `200 OK` (when `wait=true` is used):
```json
{
  "id": "1307682949281726514",
  "type": 0,
  "content": "Check out our latest business platform and grow your online visibility. https://example.com",
  "channel_id": "1199382103982910291",
  "author": {
    "bot": true,
    "id": "1307682949281726510",
    "username": "PostingBot",
    "avatar": null,
    "discriminator": "0000"
  },
  "attachments": [],
  "embeds": [],
  "mentions": [],
  "mention_roles": [],
  "pinned": false,
  "mention_everyone": false,
  "tts": false,
  "timestamp": "2026-11-18T12:00:00.000000+00:00",
  "webhook_id": "1307682949281726510"
}
```

### Post URL Construction & Public Access
- **Public Access**: `False` by default (Discord server channels require an authenticated user with access to that guild/channel).
- **URL Pattern**:
  - `https://discord.com/channels/{guild_id}/{channel_id}/{message_id}`
  - If `guild_id` is not returned, message link format: `https://discord.com/channels/@me/{channel_id}/{message_id}`

### Rate Limits & Platform Limitations
- **Rate Limit**: 5 requests per 2 seconds per webhook route (tracked via `X-RateLimit-*` response headers).
- **Message Length**: Up to 2,000 characters.

---

## 3. Reddit API

### Official Documentation
- **Official Docs**: [https://www.reddit.com/dev/api](https://www.reddit.com/dev/api)
- **Submit Reference**: [https://www.reddit.com/dev/api#POST_api_submit](https://www.reddit.com/dev/api#POST_api_submit)
- **OAuth2 Guide**: [https://github.com/reddit-archive/reddit/wiki/OAuth2](https://github.com/reddit-archive/reddit/wiki/OAuth2)

### Publishing Endpoint & HTTP Method
1. **Authentication Step**:
   - `POST https://www.reddit.com/api/v1/access_token`
   - Content-Type: `application/x-www-form-urlencoded`
   - Auth: HTTP Basic Auth (`username=REDDIT_CLIENT_ID`, `password=REDDIT_CLIENT_SECRET`)
   - Body: `grant_type=password&username=<REDDIT_USERNAME>&password=<REDDIT_PASSWORD>`
   - Response: `{"access_token": "...", "token_type": "bearer", "expires_in": 3600, "scope": "..."}`
2. **Post Publishing Step**:
   - `POST https://oauth.reddit.com/api/submit`
   - Headers:
     - `Authorization: Bearer <access_token>`
     - `User-Agent: <REDDIT_USER_AGENT>` (e.g. `AutomatedPoster/1.0.0 (by /u/username)`)
     - `Content-Type: application/x-www-form-urlencoded`

### Required Permissions & Scopes
- OAuth App Type: **"script"** created at `https://www.reddit.com/prefs/apps`.
- Scopes: `submit`, `identity`.

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

### Post URL Construction & Public Access
- **Public Access**: `True` when posting to a public subreddit (e.g., `r/test` or `r/u_<username>`).
- **URL Pattern**: Returned directly in the response field `response["json"]["data"]["url"]`.

### Rate Limits & Platform Limitations
- **Rate Limit**: 60 requests per minute with OAuth2; non-OAuth requests are heavily restricted.
- **Account Requirements**: New Reddit accounts or accounts with zero karma may trigger CAPTCHA or spam filters on certain subreddits. Testing should target `r/test` or the authenticated user's personal subreddit (`r/u_<username>`).

---

## 4. LinkedIn API

### Official Documentation
- **Official Docs**: [https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin)
- **Community Management / Posts API**: [https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://api.linkedin.com/rest/posts`
- **Headers**:
  - `Authorization: Bearer <LINKEDIN_ACCESS_TOKEN>`
  - `Linkedin-Version: 202401`
  - `X-Restli-Protocol-Version: 2.0.0`
  - `Content-Type: application/json`

### Required Permissions & Scopes
- **Member Posting Scope**: `w_member_social`
- **Organization Posting Scope**: `w_organization_social` (requires Organization Administrator access)
- Developer App created on the [LinkedIn Developer Portal](https://www.developer.linkedin.com/).

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

### Success Response Structure
HTTP `201 Created`
- Header: `x-restli-id: urn:li:share:1234567890123456789`
- Body: Empty or minimal JSON containing the created entity ID.

### Post URL Construction & Public Access
- **Public Access**: `True` (when `visibility: "PUBLIC"`).
- **URL Pattern**:
  - `https://www.linkedin.com/feed/update/{x_restli_id}/`
  - Example: `https://www.linkedin.com/feed/update/urn:li:share:1234567890123456789/`

### Rate Limits & Platform Limitations
- **Rate Limit**: 100 posts per user per day; 250 requests per minute application-wide.
- **OAuth Token Validity**: Member access tokens expire in 60 days.
- **Integration Risk**: LinkedIn requires an active app approval with the "Share on LinkedIn" or "Sign In with LinkedIn using OpenID Connect" product added to the developer application.

---

## 5. Mastodon API

### Official Documentation
- **Official Docs**: [https://docs.joinmastodon.org/methods/statuses/](https://docs.joinmastodon.org/methods/statuses/)
- **Create Status Reference**: [https://docs.joinmastodon.org/methods/statuses/#create](https://docs.joinmastodon.org/methods/statuses/#create)

### Publishing Endpoint & HTTP Method
- **Method**: `POST`
- **Endpoint**: `https://<MASTODON_INSTANCE_URL>/api/v1/statuses` (e.g. `https://mastodon.social/api/v1/statuses`)
- **Headers**:
  - `Authorization: Bearer <MASTODON_ACCESS_TOKEN>`
  - `Content-Type: application/json`

### Required Permissions & Scopes
- Scope: `write:statuses` (can be configured in Mastodon account settings under `Preferences -> Development -> New Application`).

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
  "in_reply_to_id": null,
  "sensitive": false,
  "spoiler_text": "",
  "visibility": "public",
  "language": "en",
  "uri": "https://mastodon.social/users/myuser/statuses/113504829104829104",
  "url": "https://mastodon.social/@myuser/113504829104829104",
  "replies_count": 0,
  "reblogs_count": 0,
  "favourites_count": 0,
  "content": "<p>Check out our latest business platform and grow your online visibility. <a href=\"https://example.com\" target=\"_blank\">https://example.com</a></p>",
  "account": {
    "id": "1098234",
    "username": "myuser",
    "acct": "myuser",
    "display_name": "My Name",
    "url": "https://mastodon.social/@myuser"
  }
}
```

### Post URL Construction & Public Access
- **Public Access**: `True` (public visibility).
- **URL Pattern**: Directly returned in `response["url"]` (e.g., `https://mastodon.social/@myuser/113504829104829104`).

### Rate Limits & Platform Limitations
- **Rate Limit**: 300 requests per 5 minutes per user account.
- **Instance Flexibility**: Works across any standard Mastodon / Fediverse instance (e.g., `mastodon.social`, `mstdn.io`, self-hosted).

---

## 6. Configuration Review (`app/config.py` & `.env.example`)

Both `app/config.py` and `.env.example` were verified:
- **Telegram**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` $\rightarrow$ Complete.
- **Discord**: `DISCORD_WEBHOOK_URL` $\rightarrow$ Complete.
- **Reddit**: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT`, `REDDIT_SUBREDDIT` $\rightarrow$ Complete.
- **LinkedIn**: `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_AUTHOR_URN` $\rightarrow$ Complete.
- **Mastodon**: `MASTODON_INSTANCE_URL`, `MASTODON_ACCESS_TOKEN` $\rightarrow$ Complete.

No changes were needed to `.env.example` because all required fields were accurately defined in Stage 1.
