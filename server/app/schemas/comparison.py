from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Output of POST /api/v1/comment-image-comparison-result.
# Only the fields the Claude Vision check consumes are modelled here; extra
# keys are allowed so the upstream comparator can evolve independently.
# (Handoff §3/§4: comparison_result feeds pre-vision panel targeting.)
# --------------------------------------------------------------------------- #
class CommentClaim(BaseModel):
    raw_text: str | None = None
    panel: str | None = None
    damage_type: str | None = None

    model_config = {"extra": "allow"}


class MatchedEvidence(BaseModel):
    panel_name: str | None = None
    image_name: str | None = None
    overlay_image_ref: str | None = None

    model_config = {"extra": "allow"}


class ClaimResult(BaseModel):
    claim_id: str | None = None
    claim: CommentClaim = Field(default_factory=CommentClaim)
    match_status: str | None = None
    matched_evidence: list[MatchedEvidence] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class CommentImageComparisonResponse(BaseModel):
    estimate_id: str | None = None
    claim_results: list[ClaimResult] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}
