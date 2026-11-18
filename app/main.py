"""FastAPI application entry point."""

from fastapi import FastAPI
from app.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="Automated system to publish messages across multiple third-party platforms via REST API.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/", tags=["Health"])
async def root():
    """Root health-check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "docs": "/docs",
    }
