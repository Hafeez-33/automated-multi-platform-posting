"""FastAPI application entry point."""

from fastapi import Depends, FastAPI, status
from app.config import settings
from app.schemas import PostingRequest, PostingResponse
from app.services.posting_service import PostingService

app = FastAPI(
    title=settings.APP_NAME,
    description="Automated system to publish messages across multiple third-party platforms via REST API.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


def get_posting_service() -> PostingService:
    """Dependency provider returning an instance of PostingService."""
    return PostingService()


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
    description="Validates input message with a single CTA URL and publishes it across all configured platforms.",
)
async def post_message(
    request: PostingRequest,
    posting_service: PostingService = Depends(get_posting_service),
) -> PostingResponse:
    """
    Accepts a validated promotional message and single CTA URL,
    then coordinates asynchronous publication across all target platforms.
    """
    return await posting_service.post_to_all(
        message=request.message,
        url=request.extracted_url,
    )
