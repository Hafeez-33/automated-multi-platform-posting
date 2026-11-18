"""FastAPI application entry point."""

from fastapi import FastAPI, status
from app.config import settings
from app.schemas import PostingRequest, PostingResponse

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


@app.post(
    "/posting",
    response_model=PostingResponse,
    status_code=status.HTTP_200_OK,
    tags=["Posting"],
    summary="Publish message across multiple platforms",
    description="Validates input message with a single CTA URL and prepares for multi-platform broadcasting.",
)
async def post_message(request: PostingRequest) -> PostingResponse:
    """
    Stage 2 schema verification endpoint.
    Exposes request and response models. Full multi-platform execution will be connected in Stage 5.
    """
    return PostingResponse(
        success=True,
        results=[],
    )
