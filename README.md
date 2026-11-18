# Automated Multi-Platform Posting System

A modular backend application built with **Python 3.12** and **FastAPI** that automatically publishes short promotional messages across multiple third-party platforms (Telegram, Discord, Reddit, LinkedIn, Mastodon) through their official REST APIs.

---

## Technical Stack
- **Language**: Python 3.12
- **Framework**: FastAPI
- **ASGI Server**: Uvicorn
- **Data Validation**: Pydantic v2
- **HTTP Client**: HTTPX (Asynchronous)
- **Environment**: Python-dotenv & Pydantic-Settings
- **Testing**: Pytest & Pytest-asyncio

---

## Project Structure
```
automated-posting/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── schemas.py           # Pydantic request/response schemas & validation
│   ├── config.py            # Environment & application configuration
│   ├── platforms/           # Platform API adapters
│   │   ├── base.py          # Abstract base platform adapter
│   │   ├── telegram.py      # Telegram Bot API integration
│   │   ├── discord.py       # Discord Webhook integration
│   │   ├── reddit.py        # Reddit OAuth2 API integration
│   │   ├── linkedin.py      # LinkedIn Posts API integration
│   │   └── mastodon.py      # Mastodon Status API integration
│   └── services/
│       └── posting_service.py # Multi-platform concurrent posting orchestrator
├── tests/
│   └── test_posting.py      # Automated test suite
├── .env.example             # Template for API credentials & configuration
├── .gitignore               # Git exclusion rules
├── requirements.txt         # Project dependencies
└── README.md                # Documentation & instructions
```

---

## Implementation Roadmap
- [x] **Stage 1**: Environment setup, virtual environment, and FastAPI foundation
- [ ] **Stage 2**: Pydantic schemas and strict input validation rules
- [ ] **Stage 3**: Platform API research and configuration design
- [ ] **Stage 4**: Implement platform integration adapters
- [ ] **Stage 5**: Posting orchestrator service, error handling, and test suite
- [ ] **Stage 6**: Documentation, verification, and submission readiness
