from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.schemas.comparison import ComparisonResponse


class ClaudeVisionCheckResultRequest(BaseModel):
    estimate_id: str | None = None
    # The original natural-language receptionist comment (corroboration + report header).
    comment: str | None = None
    # Output of POST /api/v1/comment-image-comparison-result (pre-vision targeting).
    comparison_result: ComparisonResponse
    # The same exterior-damage/estimate JSON (geometry parts + images.* base64).
    exterior_damage_estimate: dict[str, Any] = Field(default_factory=dict)
    # Optional image bytes (image_name/filename -> base64) for when the estimate
    # JSON's images.* blobs are stripped (e.g. a saved result.json).
    images: dict[str, str] | None = None


class ClaudeVisionCheckResultResponse(BaseModel):
    status: str
    message: str
    # An estimate-result-mirrored object (request_id / meta / geometry_info) with
    # per-panel claude_verdict and per-image damage_assessment fields added.
    data: dict[str, Any] = Field(default_factory=dict)
