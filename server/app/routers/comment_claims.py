from fastapi import APIRouter

from app.schemas.comment_claims import CommentClaimsRequest, CommentClaimsResponse
from app.services.comment_claim_extractor import extract_claims

router = APIRouter()


@router.post(
    "/extract-structured-comment-claims",
    response_model=CommentClaimsResponse,
)
async def extract_structured_comment_claims(request: CommentClaimsRequest) -> CommentClaimsResponse:
    return await extract_claims(request)
