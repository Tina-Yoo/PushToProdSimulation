from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import anthropic

from app.config import settings
from app.schemas.comparison import (
    ClaimComparisonResult,
    ClaimInput,
    ComparisonRequest,
    ComparisonResponse,
    Evidence,
    VisionHandoff,
    VisionTarget,
)
from app.services.comment_claim_extractor import normalize_damage_type, normalize_panel

# ---------------------------------------------------------------------------
# Helpers — parse exterior_damage_estimate
# ---------------------------------------------------------------------------


def _geometry_images(exterior: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        return exterior["meta"]["geometry_info"]["geometry_images"] or []
    except (KeyError, TypeError):
        return []


def _vis_damage(exterior: Dict[str, Any]) -> List[Dict[str, Any]]:
    try:
        return exterior["images"]["vis_damage"] or []
    except (KeyError, TypeError):
        return []


def _overlay_ref(vis_damage_list: List[Dict[str, Any]], image_name: str) -> Optional[str]:
    for vis in vis_damage_list:
        filename = vis.get("filename", "")
        if image_name and image_name in filename:
            return filename
    return None


def _estimate_summary(
    exterior: Dict[str, Any],
    geom_images: List[Dict[str, Any]],
    vis_damage_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Compact exterior estimate summary for Claude — no base64 data."""
    return {
        "request_id": exterior.get("request_id"),
        "geometry_images": [
            {
                "index": idx,
                "image_name": img.get("image_name"),
                "vehicle_view_type": img.get("vehicle_view_type"),
                "parts": [
                    {
                        "name": part.get("name"),
                        "damage_types": [
                            d.get("damage_type")
                            for d in part.get("damages", [])
                            if d.get("damage_type")
                        ],
                        "box_xywh": part.get("box_xywh"),
                    }
                    for part in img.get("geometry_damage_parts", [])
                ],
                "requires_review_reasons": img.get("requires_review", {}).get("reasons", []),
            }
            for idx, img in enumerate(geom_images)
        ],
        "vis_damage_filenames": [v.get("filename") for v in vis_damage_list],
    }


# ---------------------------------------------------------------------------
# Rule-based comparison
# ---------------------------------------------------------------------------


def _compare_one_claim(
    claim: ClaimInput,
    geom_images: List[Dict[str, Any]],
    vis_damage_list: List[Dict[str, Any]],
) -> ClaimComparisonResult:
    norm_panel = normalize_panel(claim.panel)
    norm_damage = normalize_damage_type(claim.damage_type)

    # ── Pass 1: direct match ─────────────────────────────────────────────
    matched_evidence: List[Evidence] = []

    if norm_panel:
        for idx, img in enumerate(geom_images):
            image_name = img.get("image_name", "")
            view_type = img.get("vehicle_view_type", "")
            review_reasons = img.get("requires_review", {}).get("reasons", [])

            for part in img.get("geometry_damage_parts", []):
                if part.get("name") != norm_panel:
                    continue
                for dmg in part.get("damages", []):
                    if dmg.get("damage_type") == norm_damage:
                        matched_evidence.append(
                            Evidence(
                                evidence_type="direct_panel_damage_match",
                                image_index=idx,
                                image_name=image_name,
                                vehicle_view_type=view_type,
                                panel_name=norm_panel,
                                damage_type=dmg.get("damage_type"),
                                damage_types=[],
                                matched_damage_types=[dmg.get("damage_type")],
                                box_xywh=dmg.get("box_xywh"),
                                requires_review_reasons=review_reasons,
                                reason=(
                                    f"코멘트의 {claim.panel}/{claim.damage_type} claim과 "
                                    f"exterior estimate 결과의 {norm_panel}/{dmg.get('damage_type')}가 "
                                    "직접 일치합니다."
                                ),
                            )
                        )

    if matched_evidence:
        return ClaimComparisonResult(
            claim_id=claim.claim_id,
            claim=claim,
            match_status="matched",
            match_confidence=0.95,
            matched_evidence=matched_evidence,
            candidate_evidence=[],
            unmatched_reason=None,
            vision_review_required=False,
            vision_targets=[],
        )

    # ── Pass 2: close_up + Unknown candidates ────────────────────────────
    candidate_evidence: List[Evidence] = []
    vision_targets: List[VisionTarget] = []

    for idx, img in enumerate(geom_images):
        if img.get("vehicle_view_type") != "close_up":
            continue

        image_name = img.get("image_name", "")
        review_reasons = img.get("requires_review", {}).get("reasons", [])

        for part in img.get("geometry_damage_parts", []):
            if part.get("name") != "Unknown":
                continue

            all_dtypes: List[str] = [
                d.get("damage_type")
                for d in part.get("damages", [])
                if d.get("damage_type")
            ]
            matched_dtypes = [dt for dt in all_dtypes if dt == norm_damage] if norm_damage else []

            # Confidence 3-tier (spec §15):
            # 0.85-0.95: damage type compatible AND review reason exists (strong candidate)
            # 0.65-0.84: damage type related but not exact
            # 0.45-0.64: weak — close_up Unknown with no matching damage type
            if matched_dtypes and review_reasons:
                cand_conf = 0.90
            elif matched_dtypes:
                cand_conf = 0.75
            elif review_reasons:
                cand_conf = 0.60
            else:
                cand_conf = 0.50

            overlay = _overlay_ref(vis_damage_list, image_name)

            candidate_evidence.append(
                Evidence(
                    evidence_type="close_up_unknown_damage_candidate",
                    image_index=idx,
                    image_name=image_name,
                    vehicle_view_type="close_up",
                    panel_name="Unknown",
                    damage_type=None,
                    damage_types=all_dtypes,
                    matched_damage_types=matched_dtypes,
                    box_xywh=part.get("box_xywh"),
                    requires_review_reasons=review_reasons,
                    reason=(
                        "이 이미지는 close_up이며 panel이 Unknown으로 매칭 실패했습니다. "
                        "claim의 손상 타입과 직접 일치하지는 않지만, 미매칭 close-up 손상 "
                        "후보이므로 Vision 검증 대상으로 전달합니다."
                    ),
                )
            )
            vision_targets.append(
                VisionTarget(
                    target_type="verify_close_up_unknown_against_claim",
                    claim_id=claim.claim_id,
                    image_index=idx,
                    image_name=image_name,
                    vehicle_view_type="close_up",
                    panel_name="Unknown",
                    overlay_image_ref=overlay,
                    candidate_confidence=cand_conf,
                    question_for_vision=(
                        f"이 close-up Unknown 손상이 {claim.claim_id}의 "
                        f"{claim.raw_text or claim.damage_type} 내용과 일치하는지 확인해 주세요."
                    ),
                    instruction=(
                        "원본 이미지, damage overlay, 코멘트 claim, exterior estimate 결과를 "
                        "함께 보고 이 손상이 claim과 일치하는지 판단해 주세요."
                    ),
                )
            )

    if candidate_evidence:
        best_conf = max(vt.candidate_confidence or 0.0 for vt in vision_targets)
        return ClaimComparisonResult(
            claim_id=claim.claim_id,
            claim=claim,
            match_status="candidate_from_close_up_unknown",
            match_confidence=best_conf,
            matched_evidence=[],
            candidate_evidence=candidate_evidence,
            unmatched_reason="No direct panel/damage match found in wide-view geometry results.",
            vision_review_required=True,
            vision_targets=vision_targets,
        )

    return ClaimComparisonResult(
        claim_id=claim.claim_id,
        claim=claim,
        match_status="unmatched",
        match_confidence=0.0,
        matched_evidence=[],
        candidate_evidence=[],
        unmatched_reason="No direct or candidate match found.",
        vision_review_required=False,
        vision_targets=[],
    )


def _overall_status(results: List[ClaimComparisonResult]) -> str:
    statuses = {r.match_status for r in results}
    if statuses == {"matched"}:
        return "matched"
    if statuses == {"unmatched"}:
        return "unmatched"
    if "candidate_from_close_up_unknown" in statuses or "needs_review" in statuses:
        return "needs_vision_review"
    return "partially_matched"


def _build_response(
    request: ComparisonRequest,
    claim_results: List[ClaimComparisonResult],
) -> ComparisonResponse:
    overall = _overall_status(claim_results)
    all_vision_targets = [t for r in claim_results for t in r.vision_targets]

    matched_count = sum(1 for r in claim_results if r.match_status == "matched")
    summary = f"{matched_count}/{len(claim_results)} claims have direct matches."
    if all_vision_targets:
        summary += (
            " Unmatched claims include close-up Unknown candidates and need Claude Vision review."
        )

    vision_handoff = VisionHandoff(
        required=bool(all_vision_targets),
        reason=(
            "Some claims were not directly matched, but close-up Unknown damage candidates exist."
            if all_vision_targets
            else None
        ),
        targets=all_vision_targets,
    )

    return ComparisonResponse(
        estimate_id=request.estimate_id,
        comparison_stage="pre_vision_targeting",
        overall_status=overall,
        summary=summary,
        claim_results=claim_results,
        vision_handoff=vision_handoff,
    )


def _rule_based_compare(
    request: ComparisonRequest,
    geom_images: List[Dict[str, Any]],
    vis_damage_list: List[Dict[str, Any]],
) -> ComparisonResponse:
    claim_results = [
        _compare_one_claim(claim, geom_images, vis_damage_list) for claim in request.claims
    ]
    return _build_response(request, claim_results)


# ---------------------------------------------------------------------------
# Claude primary flow
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a vehicle damage claim comparator for an automotive inspection system.

Given structured damage claims and an exterior image analysis summary, determine:
1. Which claims are directly confirmed (panel + damage type both match)
2. Which claims have close-up Unknown candidates for Vision review
3. Which claims are unmatched

Return ONLY a valid JSON object — no markdown, no explanation.

Required response structure:
{
  "overall_status": "<matched|partially_matched|needs_vision_review|unmatched>",
  "summary": "<concise summary string>",
  "claim_results": [
    {
      "claim_id": "<string>",
      "match_status": "<matched|candidate_from_close_up_unknown|unmatched|needs_review>",
      "match_confidence": <0.0-1.0>,
      "matched_evidence": [<Evidence>],
      "candidate_evidence": [<Evidence>],
      "unmatched_reason": "<string or null>",
      "vision_review_required": <true|false>,
      "vision_targets": [<VisionTarget>]
    }
  ],
  "vision_handoff": {
    "required": <true|false>,
    "reason": "<string or null>",
    "targets": [<VisionTarget>]
  }
}

Evidence object:
{
  "evidence_type": "direct_panel_damage_match" or "close_up_unknown_damage_candidate",
  "image_index": <int>,
  "image_name": "<filename>",
  "vehicle_view_type": "<string>",
  "panel_name": "<string>",
  "damage_type": "<string or null>",
  "damage_types": ["<string>"],
  "matched_damage_types": ["<string>"],
  "box_xywh": [<x,y,w,h>] or null,
  "requires_review_reasons": [{"source": "...", "reason": "..."}],
  "reason": "<Korean explanation>"
}

VisionTarget object:
{
  "target_type": "verify_close_up_unknown_against_claim",
  "claim_id": "<string>",
  "image_index": <int>,
  "image_name": "<filename>",
  "vehicle_view_type": "close_up",
  "panel_name": "Unknown",
  "overlay_image_ref": "<vis_damage filename or null>",
  "candidate_confidence": <0.0-1.0>,
  "question_for_vision": "<Korean question>",
  "instruction": "<Korean instruction>"
}

Matching rules:
- Direct match: normalize claim.panel to standard code (e.g. back_bumper→Back-bumper, rear_door→Back-door-left/right) AND normalize claim.damage_type (e.g. deep_scratch→DeepScratched, dent→Crushed) — both must match a geometry_damage_part entry
- Candidate: vehicle_view_type=="close_up" AND part.name=="Unknown" — only when no direct match exists
- Unmatched: neither condition met

Confidence:
- Direct match: 0.90–0.99
- Candidate with compatible damage types: 0.65–0.84
- Candidate without compatible damage types: 0.45–0.64
- Unmatched: 0.0
"""


async def _claude_compare(
    request: ComparisonRequest,
    summary: Dict[str, Any],
    rule_result: ComparisonResponse,
) -> ComparisonResponse:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_content = json.dumps(
        {
            "estimate_id": request.estimate_id,
            "comment": request.comment,
            "claims": [c.model_dump() for c in request.claims],
            "exterior_estimate_summary": summary,
            "rule_based_reference": {
                "claim_comparisons": [
                    {
                        "claim_id": r.claim_id,
                        "normalized_panel": normalize_panel(r.claim.panel),
                        "normalized_damage": normalize_damage_type(r.claim.damage_type),
                        "match_status": r.match_status,
                        "match_confidence": r.match_confidence,
                    }
                    for r in rule_result.claim_results
                ]
            },
        },
        ensure_ascii=False,
    )

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    text = response.content[0].text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    raw = json.loads(text)

    # Reconstruct claim_results, injecting original claim objects
    claim_map = {c.claim_id: c for c in request.claims}
    claim_results: List[ClaimComparisonResult] = []

    for cr in raw.get("claim_results", []):
        cid = cr.get("claim_id", "")
        original_claim = claim_map.get(cid)
        if not original_claim:
            continue
        claim_results.append(
            ClaimComparisonResult(
                claim_id=cid,
                claim=original_claim,
                match_status=cr.get("match_status", "unmatched"),
                match_confidence=float(cr.get("match_confidence", 0.0)),
                matched_evidence=[Evidence.model_validate(e) for e in cr.get("matched_evidence", [])],
                candidate_evidence=[Evidence.model_validate(e) for e in cr.get("candidate_evidence", [])],
                unmatched_reason=cr.get("unmatched_reason"),
                vision_review_required=bool(cr.get("vision_review_required", False)),
                vision_targets=[VisionTarget.model_validate(vt) for vt in cr.get("vision_targets", [])],
            )
        )

    # Safety net: if Claude omitted any claims, fill them from rule_result
    returned_ids = {r.claim_id for r in claim_results}
    for rule_cr in rule_result.claim_results:
        if rule_cr.claim_id not in returned_ids:
            claim_results.append(rule_cr)

    vh = raw.get("vision_handoff", {})
    vision_handoff = VisionHandoff(
        required=bool(vh.get("required", False)),
        reason=vh.get("reason"),
        targets=[VisionTarget.model_validate(vt) for vt in vh.get("targets", [])],
    )

    return ComparisonResponse(
        estimate_id=request.estimate_id,
        comparison_stage="pre_vision_targeting",
        overall_status=raw.get("overall_status", "unmatched"),
        summary=raw.get("summary", ""),
        claim_results=claim_results,
        vision_handoff=vision_handoff,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def compare_claims(request: ComparisonRequest) -> ComparisonResponse:
    geom_images = _geometry_images(request.exterior_damage_estimate)
    vis_damage_list = _vis_damage(request.exterior_damage_estimate)

    rule_result = _rule_based_compare(request, geom_images, vis_damage_list)

    if not settings.anthropic_api_key:
        return rule_result

    try:
        summary = _estimate_summary(request.exterior_damage_estimate, geom_images, vis_damage_list)
        return await _claude_compare(request, summary, rule_result)
    except Exception:
        return rule_result
