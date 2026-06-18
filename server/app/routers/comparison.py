from fastapi import APIRouter

from app.schemas.comparison import ComparisonRequest, ComparisonResponse
from app.services.comment_image_comparator import compare_claims

router = APIRouter()


@router.post(
    "/comment-image-comparison-result",
    response_model=ComparisonResponse,
)
async def comment_image_comparison_result(request: ComparisonRequest) -> ComparisonResponse:
    return await compare_claims(request)
