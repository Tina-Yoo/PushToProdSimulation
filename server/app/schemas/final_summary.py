from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FinalSummaryRequest(BaseModel):
    estimate_id: Optional[str] = None
    document_no: Optional[str] = None
    issue_date: Optional[str] = None
    vehicle_category: Optional[str] = None
    vehicle_info: Optional[Dict[str, Any]] = None
    claude_vision_check_result: Optional[Dict[str, Any]] = None


class DocumentInfo(BaseModel):
    document_no: Optional[str] = None
    issue_date: Optional[str] = None


class VehicleInfo(BaseModel):
    vehicle_no: Optional[str] = None
    vehicle_name: Optional[str] = None
    vehicle_category: Optional[str] = None


class AnalysisResult(BaseModel):
    overall_status: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    total_damage_count: int = 0
    estimate_damage_count: int = 0
    review_damage_count: int = 0
    image_count: int = 0
    comment_count: int = 0
    overall_confidence: Optional[float] = None
    model: Optional[str] = None


class EvidenceImage(BaseModel):
    image_name: str


class DamageSection(BaseModel):
    section_no: int
    damage_item_id: str
    panel: Optional[str] = None
    panel_label: Optional[str] = None
    damage_types: List[str] = []
    damage_type_labels: List[str] = []
    repair_types: List[str] = []
    repair_type_labels: List[str] = []
    confidence: Optional[float] = None
    confidence_percent: Optional[int] = None
    reasoning: Optional[str] = None
    comment_claim_id: Optional[str] = None
    evidence_images: List[EvidenceImage] = []
    damage_confidences: Dict[str, float] = {}
    damage_verdicts: List[Dict[str, Any]] = []
    requires_review: bool = False
    requires_review_reasons: List[Any] = []
    included_in_estimate: bool = True


class EstimateRow(BaseModel):
    no: int
    damage_item_id: str
    damage_part: Optional[str] = None
    repair_content: str
    quantity: int = 1
    unit_price: Optional[int] = None
    supply_amount: Optional[int] = None
    confidence: Optional[float] = None
    evidence_images: List[EvidenceImage] = []
    pricing_status: str


class EstimateTotals(BaseModel):
    currency: str = "KRW"
    supply_amount: int
    vat_rate: float = 0.1
    vat_amount: int
    total_amount: int


class EstimateSheet(BaseModel):
    rows: List[EstimateRow] = []
    totals: EstimateTotals


class FinalSummaryResponse(BaseModel):
    estimate_id: Optional[str] = None
    status: str
    message: str
    document_info: Optional[DocumentInfo] = None
    vehicle_info: Optional[VehicleInfo] = None
    analysis_result: Optional[AnalysisResult] = None
    damage_sections: List[DamageSection] = []
    estimate_sheet: Optional[EstimateSheet] = None
    pending_inputs: List[str] = []
