from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ClaimInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim_id: str
    side: Optional[str] = None
    area: Optional[str] = None
    panel: Optional[str] = None
    damage_type: Optional[str] = None
    severity: Optional[str] = None
    raw_text: Optional[str] = None
    confidence: Optional[float] = None


class Evidence(BaseModel):
    evidence_type: str
    image_index: Optional[int] = None
    image_name: Optional[str] = None
    vehicle_view_type: Optional[str] = None
    panel_name: Optional[str] = None
    damage_type: Optional[str] = None
    damage_types: List[str] = []
    matched_damage_types: List[str] = []
    box_xywh: Optional[List[float]] = None
    requires_review_reasons: List[Any] = []
    reason: str = ""


class VisionTarget(BaseModel):
    target_type: str
    claim_id: str
    image_index: Optional[int] = None
    image_name: Optional[str] = None
    vehicle_view_type: Optional[str] = None
    panel_name: Optional[str] = None
    overlay_image_ref: Optional[str] = None
    candidate_confidence: Optional[float] = None
    question_for_vision: Optional[str] = None
    instruction: Optional[str] = None


class ClaimComparisonResult(BaseModel):
    claim_id: str
    claim: ClaimInput
    match_status: str
    match_confidence: float
    matched_evidence: List[Evidence] = []
    candidate_evidence: List[Evidence] = []
    unmatched_reason: Optional[str] = None
    vision_review_required: bool
    vision_targets: List[VisionTarget] = []


class VisionHandoff(BaseModel):
    required: bool
    reason: Optional[str] = None
    targets: List[VisionTarget] = []


class ComparisonRequest(BaseModel):
    estimate_id: Optional[str] = None
    comment: Optional[str] = None
    claims: List[ClaimInput]
    exterior_damage_estimate: Dict[str, Any]


class ComparisonResponse(BaseModel):
    estimate_id: Optional[str] = None
    comparison_stage: str = "pre_vision_targeting"
    overall_status: str
    summary: str
    claim_results: List[ClaimComparisonResult]
    vision_handoff: VisionHandoff
