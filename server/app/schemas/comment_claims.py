from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class CommentClaimsRequest(BaseModel):
    estimate_id: Optional[str] = None
    comment: str


class ClaimItem(BaseModel):
    claim_id: str
    side: Optional[str] = None
    area: Optional[str] = None
    panel: Optional[str] = None
    damage_type: Optional[str] = None
    severity: Optional[str] = None
    raw_text: str
    confidence: float


class CommentClaimsResponse(BaseModel):
    estimate_id: Optional[str] = None
    comment: str
    extractor: str
    model: Optional[str] = None
    llm_error: Optional[str] = None
    claims: List[ClaimItem]
