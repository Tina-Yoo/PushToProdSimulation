from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.final_summary import (
    AnalysisResult,
    DamageSection,
    DocumentInfo,
    EstimateRow,
    EstimateSheet,
    EstimateTotals,
    EvidenceImage,
    FinalSummaryRequest,
    FinalSummaryResponse,
    VehicleInfo,
)

# ---------------------------------------------------------------------------
# Reference tables
# ---------------------------------------------------------------------------

VEHICLE_COST_TABLE: Dict[str, Dict[str, int]] = {
    "경차":    {"PanelRepairCost": 110_000, "PolishingCost":  70_000, "InteriorCleaningCost": 100_000},
    "소형":    {"PanelRepairCost": 115_000, "PolishingCost":  70_000, "InteriorCleaningCost": 100_000},
    "준중형":  {"PanelRepairCost": 125_000, "PolishingCost":  90_000, "InteriorCleaningCost": 100_000},
    "중형":    {"PanelRepairCost": 135_000, "PolishingCost": 100_000, "InteriorCleaningCost": 100_000},
    "준대형":  {"PanelRepairCost": 150_000, "PolishingCost": 115_000, "InteriorCleaningCost": 150_000},
    "특대형":  {"PanelRepairCost": 174_000, "PolishingCost": 125_000, "InteriorCleaningCost": 150_000},
    "중형SUV": {"PanelRepairCost": 164_000, "PolishingCost": 125_000, "InteriorCleaningCost": 150_000},
    "대형SUV": {"PanelRepairCost": 174_000, "PolishingCost": 125_000, "InteriorCleaningCost": 150_000},
    "RV/승합": {"PanelRepairCost": 164_000, "PolishingCost": 125_000, "InteriorCleaningCost": 150_000},
    "수입차":  {"PanelRepairCost": 220_000, "PolishingCost": 160_000, "InteriorCleaningCost": 200_000},
}

REPAIR_TYPE_COST_KEY: Dict[str, str] = {
    "Polishing":        "PolishingCost",
    "Repainting":       "PanelRepairCost",
    "BodyRepair":       "PanelRepairCost",
    "InteriorCleaning": "InteriorCleaningCost",
}

PANEL_LABELS: Dict[str, str] = {
    "Back-bumper":         "뒤범퍼",
    "Back-door-left":      "뒷문 (운전석)",
    "Back-door-right":     "뒷문 (조수석)",
    "Back-wheel-left":     "뒷바퀴 (운전석)",
    "Back-wheel-right":    "뒷바퀴 (조수석)",
    "Back-window-left":    "뒤창문 (운전석)",
    "Back-window-right":   "뒤창문 (조수석)",
    "Back-windshield":     "뒤유리",
    "Fender-left":         "휀더 (운전석)",
    "Fender-right":        "휀더 (조수석)",
    "Front-bumper":        "앞범퍼",
    "Front-door-left":     "앞문 (운전석)",
    "Front-door-right":    "앞문 (조수석)",
    "Front-wheel-left":    "앞바퀴 (운전석)",
    "Front-wheel-right":   "앞바퀴 (조수석)",
    "Front-window-left":   "앞창문 (운전석)",
    "Front-window-right":  "앞창문 (조수석)",
    "Grille":              "그릴",
    "Headlight-left":      "헤드라이트 (운전석)",
    "Headlight-right":     "헤드라이트 (조수석)",
    "Hood":                "후드",
    "License-plate":       "번호판",
    "Mirror-left":         "미러 (운전석)",
    "Mirror-right":        "미러 (조수석)",
    "Quarter-panel-left":  "쿼터패널 (운전석)",
    "Quarter-panel-right": "쿼터패널 (조수석)",
    "Rocker-panel-left":   "로커패널 (운전석)",
    "Rocker-panel-right":  "로커패널 (조수석)",
    "Roof":                "루프",
    "Tail-light-left":     "테일라이트 (운전석)",
    "Tail-light-right":    "테일라이트 (조수석)",
    "Trunk":               "트렁크",
    "Windshield":          "앞유리",
}

DAMAGE_TYPE_LABELS: Dict[str, str] = {
    "Chip":           "칩",
    "Stain":          "얼룩",
    "MudSplash":      "흙탕물",
    "Swirl":          "스월마크",
    "MicroScratched": "미세 스크래치",
    "Scratched":      "스크래치",
    "TouchupPaint":   "터치업 페인트",
    "DeepScratched":  "깊은 스크래치",
    "RustSurface":    "표면 녹",
    "RustDeep":       "심층 녹",
    "Crack":          "균열",
    "TireDamage":     "타이어 손상",
    "Crushed":        "찌그러짐",
    "Separated":      "분리",
    "Breakage":       "파손",
    "Marker":         "마커",
}

REPAIR_TYPE_LABELS: Dict[str, str] = {
    "Polishing":        "광택",
    "Repainting":       "도색",
    "BodyRepair":       "판금",
    "InteriorCleaning": "실내 청소",
}

VAT_RATE = 0.1

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _included_in_estimate(panel: Dict[str, Any]) -> bool:
    """claude_verdict.agree = false → exclude. True or missing → include."""
    verdict = panel.get("claude_verdict") or {}
    agree = verdict.get("agree")
    return agree is not False


def _unit_price(repair_types: List[str], cost_table: Dict[str, int]) -> Optional[int]:
    """Sum costs for unique cost-key types mapped from repair_types."""
    cost_keys = {REPAIR_TYPE_COST_KEY.get(rt) for rt in repair_types} - {None}
    if not cost_keys:
        return None
    return sum(cost_table.get(k, 0) for k in cost_keys) or None


def _build_damage_section(idx: int, panel: Dict[str, Any]) -> DamageSection:
    name = panel.get("name")
    damages: List[str] = panel.get("damages") or []
    repair_types: List[str] = panel.get("repair_types") or []
    review_reasons: List[Any] = panel.get("requires_review_reasons") or []
    verdict: Dict[str, Any] = panel.get("claude_verdict") or {}

    confidence = verdict.get("confidence")

    return DamageSection(
        section_no=idx,
        damage_item_id=f"damage_{idx:03d}",
        panel=name,
        panel_label=PANEL_LABELS.get(name) if name else None,
        damage_types=damages,
        damage_type_labels=[DAMAGE_TYPE_LABELS.get(d, d) for d in damages],
        repair_types=repair_types,
        repair_type_labels=[REPAIR_TYPE_LABELS.get(rt, rt) for rt in repair_types],
        confidence=confidence,
        confidence_percent=round(confidence * 100) if confidence is not None else None,
        reasoning=verdict.get("reasoning"),
        comment_claim_id=verdict.get("comment_corroboration"),
        evidence_images=[
            EvidenceImage(image_name=img)
            for img in (verdict.get("evidence_images") or [])
        ],
        damage_confidences={
            k: v for k, v in (verdict.get("damage_confidences") or {}).items()
            if v is not None
        },
        damage_verdicts=verdict.get("damage_verdicts") or [],
        requires_review=bool(review_reasons),
        requires_review_reasons=review_reasons,
        included_in_estimate=_included_in_estimate(panel),
    )


def _repair_content(damage_type_labels: List[str], repair_type_labels: List[str]) -> str:
    dmg = ", ".join(damage_type_labels)
    rep = ", ".join(repair_type_labels)
    if dmg and rep:
        return f"{dmg} {rep}"
    return dmg or rep


def _build_estimate_row(
    no: int,
    section: DamageSection,
    cost_table: Dict[str, int],
) -> EstimateRow:
    unit = _unit_price(section.repair_types, cost_table)
    supply = unit  # quantity = 1

    return EstimateRow(
        no=no,
        damage_item_id=section.damage_item_id,
        damage_part=section.panel_label or section.panel,
        repair_content=_repair_content(section.damage_type_labels, section.repair_type_labels),
        quantity=1,
        unit_price=unit,
        supply_amount=supply,
        confidence=section.confidence,
        evidence_images=section.evidence_images,
        pricing_status="priced" if unit is not None else "unpriced",
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_final_summary(request: FinalSummaryRequest) -> FinalSummaryResponse:
    pending_inputs: List[str] = []

    vision_result = request.claude_vision_check_result
    if not vision_result:
        pending_inputs.append("claude_vision_check_result")

    cost_table = VEHICLE_COST_TABLE.get(request.vehicle_category or "")
    if not cost_table:
        pending_inputs.append("valid_vehicle_category")

    if pending_inputs:
        return FinalSummaryResponse(
            estimate_id=request.estimate_id,
            status="partial",
            message="Required inputs are missing.",
            pending_inputs=pending_inputs,
        )

    # ── Extract from Vision result ────────────────────────────────────────
    data: Dict[str, Any] = vision_result.get("data") or {}
    meta: Dict[str, Any] = data.get("meta") or {}

    estimate_id = request.estimate_id or data.get("estimate_id")

    # vehicle_info: Vision vehicle_info + request vehicle_info + vehicle_category
    vision_vi: Dict[str, Any] = meta.get("vehicle_info") or {}
    req_vi: Dict[str, Any] = request.vehicle_info or {}
    vehicle_info = VehicleInfo(
        vehicle_no=vision_vi.get("vehicle_no") or req_vi.get("vehicle_no"),
        vehicle_name=req_vi.get("vehicle_name") or vision_vi.get("vehicle_name"),
        vehicle_category=request.vehicle_category,
    )

    damaged_panels: List[Dict[str, Any]] = meta.get("damaged_panels") or []
    geom_images: List[Any] = (meta.get("geometry_info") or {}).get("geometry_images") or []
    comment_claims: List[Any] = meta.get("comment_claims") or []

    # ── damage_sections ───────────────────────────────────────────────────
    damage_sections = [
        _build_damage_section(i + 1, panel) for i, panel in enumerate(damaged_panels)
    ]

    # ── analysis_result ───────────────────────────────────────────────────
    included = [s for s in damage_sections if s.included_in_estimate]
    reviewed = [s for s in damage_sections if s.requires_review]
    confidences = [s.confidence for s in damage_sections if s.confidence is not None]
    overall_conf: Optional[float] = (
        round(sum(confidences) / len(confidences), 4) if confidences else None
    )

    analysis_result = AnalysisResult(
        overall_status=meta.get("overall_status"),
        headline=meta.get("headline"),
        summary=meta.get("summary"),
        total_damage_count=len(damage_sections),
        estimate_damage_count=len(included),
        review_damage_count=len(reviewed),
        image_count=len(geom_images),
        comment_count=len(comment_claims),
        overall_confidence=overall_conf,
        model=meta.get("model"),
    )

    # ── estimate_sheet (included_in_estimate = True only) ─────────────────
    rows: List[EstimateRow] = []
    row_no = 1
    for section in damage_sections:
        if section.included_in_estimate:
            rows.append(_build_estimate_row(row_no, section, cost_table))
            row_no += 1

    supply_total = sum(r.supply_amount for r in rows if r.supply_amount is not None)
    vat = round(supply_total * VAT_RATE)

    estimate_sheet = EstimateSheet(
        rows=rows,
        totals=EstimateTotals(
            currency="KRW",
            supply_amount=supply_total,
            vat_rate=VAT_RATE,
            vat_amount=vat,
            total_amount=supply_total + vat,
        ),
    )

    return FinalSummaryResponse(
        estimate_id=estimate_id,
        status="ready",
        message="Final estimate document data is ready.",
        document_info=DocumentInfo(
            document_no=request.document_no,
            issue_date=request.issue_date,
        ),
        vehicle_info=vehicle_info,
        analysis_result=analysis_result,
        damage_sections=damage_sections,
        estimate_sheet=estimate_sheet,
        pending_inputs=[],
    )
