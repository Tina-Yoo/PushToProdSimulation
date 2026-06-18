from __future__ import annotations

from fastapi import APIRouter

from app.schemas.claude_vision_check import (
    ClaudeVisionCheckResultRequest,
    ClaudeVisionCheckResultResponse,
)
from app.services.claude_vision_check import build_claude_vision_check_result


router = APIRouter(tags=["claude vision check"])


@router.post(
    "/claude-vision-check-result",
    response_model=ClaudeVisionCheckResultResponse,
)
async def claude_vision_check_result(
    request: ClaudeVisionCheckResultRequest,
) -> ClaudeVisionCheckResultResponse:
    return await build_claude_vision_check_result(request)
