from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from app.schemas.comparison import ComparisonResponse
from app.schemas.claude_vision_check import (
    ClaudeVisionCheckResultRequest,
    ClaudeVisionCheckResultResponse,
)
from app.services.vision_helpers import (
    build_overlay_lookup,
    extract_geometry_images,
    extract_image_identity_tokens,
    extract_json_object,
    extract_text_content,
)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Exterior panel categories (estimate-style names). Used to keep Vision honest.
PANEL_VOCABULARY = [
    "Quarter-panel", "Front-wheel", "Back-window", "Trunk", "Front-door",
    "Rocker-panel", "Grille", "Windshield", "Front-window", "Back-door",
    "Headlight", "Back-wheel", "Back-windshield", "Hood", "Fender",
    "Tail-light", "License-plate", "Front-bumper", "Back-bumper", "Mirror",
    "Roof",
]

MAX_JUDGED_IMAGES = 8   # per panel: cap images Vision actually judges
MAX_WIDE_REFS = 3       # per panel: extra whole-car context images
LOW_CONF = 0.5          # confidence below this is flagged


# --------------------------------------------------------------------------- #
# Vision structured output (per panel)
# --------------------------------------------------------------------------- #
class DamageTypeVerdict(BaseModel):
    damage_type: str
    agree: bool
    confidence: float = 0.0
    reasoning: str = ""


class PanelImageVerdict(BaseModel):
    image_name: str
    agree: bool
    confidence: float = 0.0
    reasoning: str = ""


class PanelVisionVerdict(BaseModel):
    overall_agree: bool
    overall_confidence: float = 0.0
    overall_reasoning: str = ""
    damage_type_verdicts: list[DamageTypeVerdict] = []
    per_image: list[PanelImageVerdict] = []


def _clamp(x: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(x))), 3)
    except (TypeError, ValueError):
        return 0.0


# --------------------------------------------------------------------------- #
# image bytes resolution (estimate base64 first, request.images second)
# --------------------------------------------------------------------------- #
def _media_type(name: str) -> str:
    return "image/png" if name.lower().endswith(".png") else "image/jpeg"


def _is_real_b64(data: Any) -> bool:
    return isinstance(data, str) and bool(data) and not data.startswith("<base64:")


class ImageStore:
    def __init__(self, estimate: dict[str, Any], request_images: dict[str, str] | None):
        self.request_images = request_images or {}
        self.by_filename: dict[str, str] = {}
        self.by_token: dict[str, str] = {}
        self.exterior: list[tuple[str, str]] = []
        for group, items in (estimate.get("images") or {}).items():
            for item in items or []:
                filename = item.get("filename")
                data = item.get("data")
                if not filename or not _is_real_b64(data):
                    continue
                self.by_filename[filename] = data
                for token in extract_image_identity_tokens(filename):
                    self.by_token.setdefault(token, data)
                if group == "vis_exterior":
                    self.exterior.append((filename, data))

    def resolve(self, key: str | None) -> tuple[str, str] | None:
        if not key:
            return None
        if _is_real_b64(self.request_images.get(key)):
            return self.request_images[key], _media_type(key)
        if key in self.by_filename:
            return self.by_filename[key], _media_type(key)
        if key in self.by_token:
            return self.by_token[key], _media_type(key)
        return None

    def wide_refs(self, limit: int = MAX_WIDE_REFS) -> list[tuple[str, str]]:
        return self.exterior[:limit]


# --------------------------------------------------------------------------- #
# estimate / comment indexing
# --------------------------------------------------------------------------- #
def _norm(value: str | None) -> str:
    if not value:
        return ""
    return value.strip().lower().replace("-", "_").replace(" ", "_").replace("back", "rear")


def build_panel_evidence(estimate: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    """panel_name -> {image_name: [damage_types seen in that image]}."""
    panel_map: dict[str, dict[str, set[str]]] = {}
    for image in extract_geometry_images(estimate):
        image_name = image.get("image_name")
        for part in image.get("geometry_damage_parts", []) or []:
            pname = part.get("name")
            if not pname or pname == "Unknown":
                continue
            dts = {d.get("damage_type") for d in part.get("damages", []) or [] if d.get("damage_type")}
            panel_map.setdefault(pname, {}).setdefault(image_name, set()).update(dts)
    return {p: {img: sorted(d) for img, d in imgs.items()} for p, imgs in panel_map.items()}


def build_comment_index(
    comparison: ComparisonResponse,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """(normalized_panel -> claim metadata, comment_claims echo list)."""
    panel_to_claim: dict[str, dict[str, Any]] = {}
    echo: list[dict[str, Any]] = []
    for cr in comparison.claim_results:
        corroborated = None
        for ev in cr.matched_evidence:
            if ev.panel_name:
                panel_to_claim[_norm(ev.panel_name)] = {
                    "claim_id": cr.claim_id,
                    "raw_text": cr.claim.raw_text,
                    "evidence_image_names": collect_evidence_image_names(cr.matched_evidence),
                }
                corroborated = ev.panel_name
                break
        echo.append({
            "claim_id": cr.claim_id,
            "raw_text": cr.claim.raw_text,
            "panel": cr.claim.panel,
            "damage_type": cr.claim.damage_type,
            "comparison_status": cr.match_status,
            "corroborated_panel": corroborated,
        })
    return panel_to_claim, echo


def collect_evidence_image_names(evidence_items: list[Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for evidence in evidence_items:
        image_name = getattr(evidence, "image_name", None)
        if image_name and image_name not in seen:
            names.append(image_name)
            seen.add(image_name)
    return names


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
async def build_claude_vision_check_result(
    request: ClaudeVisionCheckResultRequest,
) -> ClaudeVisionCheckResultResponse:
    estimate = request.exterior_damage_estimate
    comparison = request.comparison_result
    comment = request.comment
    meta = estimate.get("meta", {}) or {}

    store = ImageStore(estimate, request.images)
    overlay_lookup = build_overlay_lookup(estimate)
    panel_evidence = build_panel_evidence(estimate)
    panel_to_claim, comment_claims = build_comment_index(comparison)

    use_vision = bool(ANTHROPIC_API_KEY)
    panel_verdicts: dict[str, PanelVisionVerdict | None] = {}
    vision_calls = 0

    # --- per-panel Vision audit over every detected exterior damage ---------
    damaged_panels_out: list[dict[str, Any]] = []
    for panel in meta.get("damaged_panels", []) or []:
        name = panel.get("name")
        damages = panel.get("damages", []) or []
        evidence_image_names = list((panel_evidence.get(name) or {}).keys())[:MAX_JUDGED_IMAGES]
        corr = panel_to_claim.get(_norm(name))
        images = collect_panel_images(evidence_image_names, store, overlay_lookup)
        evidence_image_refs = resolve_evidence_image_refs(
            evidence_image_names, overlay_lookup, preferred_image_names=(corr or {}).get("evidence_image_names")
        )

        verdict: PanelVisionVerdict | None = None
        if use_vision and images and damages:
            verdict = await ask_panel_vision(
                panel_name=name, damage_types=damages,
                comment_hint=corr["raw_text"] if corr else None, images=images,
            )
            if verdict is not None:
                vision_calls += 1
        panel_verdicts[name] = verdict

        damaged_panels_out.append({
            "name": name,
            "damages": damages,
            "repair_types": panel.get("repair_types", []) or [],
            "requires_review_reasons": [
                r.get("reason") for r in ((panel.get("requires_review", {}) or {}).get("reasons", []) or [])
                if r.get("reason")
            ],
            "claude_verdict": build_claude_verdict(
                verdict, damages, evidence_image_refs, corr, had_images=bool(images), use_vision=use_vision
            ),
        })

    decider = "vision" if (use_vision and vision_calls) else "rule_fallback"

    # --- mirror geometry_images, add per-image damage_assessment ------------
    geometry_images_out = build_geometry_images(
        estimate, panel_evidence, panel_verdicts, panel_to_claim, overlay_lookup
    )

    stats = build_stats(damaged_panels_out)
    overall_status = build_overall_status(damaged_panels_out, decider)
    data = {
        "request_id": estimate.get("request_id"),
        "estimate_id": request.estimate_id or comparison.estimate_id or estimate.get("request_id"),
        "comment": comment,
        "meta": {
            "vehicle_info": meta.get("vehicle_info", {}),
            "overall_status": overall_status,
            "headline": build_headline(overall_status, stats),
            "summary": build_narrative(comment, meta, damaged_panels_out, stats, decider, overall_status),
            "stats": stats,
            "decider": decider,
            "model": CLAUDE_MODEL if decider == "vision" else None,
            "comment_claims": comment_claims,
            "damaged_panels": damaged_panels_out,
            "geometry_info": {"geometry_images": geometry_images_out},
        },
    }
    return ClaudeVisionCheckResultResponse(
        status="completed",
        message="Claude Vision check completed.",
        data=data,
    )


# --------------------------------------------------------------------------- #
# image assembly for a panel
# --------------------------------------------------------------------------- #
def collect_panel_images(
    evidence_images: list[str], store: ImageStore, overlay_lookup: dict[str, str]
) -> list[tuple[str, str, str, str]]:
    """Return [(image_name, label, b64, media_type)] — judged overlays + wide refs.

    Judged images carry their real image_name; wide refs use '' so Vision does not
    return per_image verdicts for them.
    """
    out: list[tuple[str, str, str, str]] = []
    for iname in evidence_images:
        resolved = store.resolve(overlay_lookup.get(iname)) or store.resolve(iname)
        if resolved:
            out.append((iname, f"EVIDENCE image_name={iname}", resolved[0], resolved[1]))
    judged = {iname for iname, *_ in out}
    for filename, b64 in store.wide_refs():
        if filename in judged:
            continue
        out.append(("", f"FAR VIEW (context only) {filename}", b64, _media_type(filename)))
    return out


def resolve_evidence_image_refs(
    evidence_image_names: list[str],
    overlay_lookup: dict[str, str],
    preferred_image_names: list[str] | None = None,
) -> list[str]:
    # The API tracks evidence by original image_name, but the frontend should
    # display the estimate damage overlay when one exists. For display evidence,
    # prefer close-up damage overlays for the panel over warped wide-view
    # overlays, even if the comment match came from a wide-view image.
    close_up_refs = dedupe_refs(
        overlay_lookup.get(image_name)
        for image_name in evidence_image_names
        if is_close_up_damage_overlay(overlay_lookup.get(image_name))
    )
    if close_up_refs:
        return close_up_refs

    image_names = preferred_image_names or evidence_image_names
    refs: list[str] = []
    seen: set[str] = set()
    for image_name in image_names:
        ref = overlay_lookup.get(image_name) or image_name
        if ref and ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def is_close_up_damage_overlay(ref: str | None) -> bool:
    if not ref:
        return False
    return "_damage_" in ref and "_warped_damage_" not in ref


def dedupe_refs(refs: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        if ref and ref not in seen:
            out.append(ref)
            seen.add(ref)
    return out


# --------------------------------------------------------------------------- #
# Claude Vision (per panel)
# --------------------------------------------------------------------------- #
def build_system_prompt() -> str:
    return (
        "You audit an automated vehicle exterior-damage estimate. For ONE panel and its "
        "DETECTED DAMAGE TYPES, decide whether each detection is real and located on that "
        "panel, and how confident you are.\n"
        "- You get EVIDENCE images (close-ups / wide views with damage marked) plus some "
        "FAR VIEW context images. Judge ONLY the named panel.\n"
        f"- The panel name is given and is one of: {', '.join(PANEL_VOCABULARY)} (optionally with "
        "-left/-right). Do not relocate the damage to another panel; judge agreement for THIS panel.\n"
        "- For EACH damage type return agree (is this damage type really present on this panel?) "
        "and a 0..1 confidence.\n"
        "- Also return a per-image read: for each EVIDENCE image (by image_name), does it show "
        "this panel's damage, with a 0..1 confidence. Do NOT return entries for FAR VIEW context.\n"
        "- A receptionist comment may corroborate; treat it as a hint, not proof.\n"
        "- All reasoning must be concise Korean.\n"
        "- Return ONLY valid JSON, no markdown:\n"
        '{"overall_agree": bool, "overall_confidence": number, "overall_reasoning": string, '
        '"damage_type_verdicts": [{"damage_type": string, "agree": bool, "confidence": number, "reasoning": string}], '
        '"per_image": [{"image_name": string, "agree": bool, "confidence": number, "reasoning": string}]}'
    )


def build_user_text(panel_name: str, damage_types: list[str], comment_hint: str | None) -> str:
    hint = f"RECEPTIONIST COMMENT (corroboration hint): {comment_hint}\n" if comment_hint else ""
    return (
        f"PANEL: {panel_name}\n"
        f"DETECTED DAMAGE TYPES: {', '.join(damage_types)}\n"
        f"{hint}"
        "TASK: For this panel, judge each damage type (agree + confidence) and give a per-image read."
    )


async def ask_panel_vision(
    *,
    panel_name: str,
    damage_types: list[str],
    comment_hint: str | None,
    images: list[tuple[str, str, str, str]],
) -> PanelVisionVerdict | None:
    content: list[dict[str, Any]] = []
    for _iname, label, b64, media_type in images:
        content.append({"type": "text", "text": label})
        content.append({"type": "image", "source": {
            "type": "base64", "media_type": media_type, "data": b64}})
    content.append({"type": "text", "text": build_user_text(panel_name, damage_types, comment_hint)})

    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 2000,
        "system": build_system_prompt(),
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(ANTHROPIC_MESSAGES_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        parsed = json.loads(extract_json_object(extract_text_content(data)))
        return PanelVisionVerdict.model_validate(parsed)
    except (httpx.HTTPError, ValueError, ValidationError, json.JSONDecodeError):
        return None


# --------------------------------------------------------------------------- #
# verdict / output builders
# --------------------------------------------------------------------------- #
def build_claude_verdict(
    verdict: PanelVisionVerdict | None,
    damages: list[str],
    evidence_images: list[str],
    corr: dict[str, Any] | None,
    *,
    had_images: bool,
    use_vision: bool,
) -> dict[str, Any]:
    comment_id = corr["claim_id"] if corr else None
    if verdict is None:
        reason = ("Vision 미수행 — 사람 검토가 필요합니다."
                  if not use_vision else
                  ("이미지 바이트가 없어 검증하지 못했습니다." if not had_images
                   else "Vision 호출 실패로 검증하지 못했습니다."))
        return {
            "agree": None, "confidence": None,
            "damage_confidences": {d: None for d in damages},
            "damage_verdicts": [
                {"damage_type": d, "agree": None, "confidence": None, "reasoning": ""}
                for d in damages
            ],
            "reasoning": reason,
            "evidence_images": evidence_images,
            "comment_corroboration": comment_id,
        }

    by_type = {dv.damage_type: dv for dv in verdict.damage_type_verdicts}
    damage_verdicts = []
    damage_confidences = {}
    for d in damages:
        dv = by_type.get(d)
        conf = _clamp(dv.confidence) if dv else None
        damage_confidences[d] = conf
        damage_verdicts.append({
            "damage_type": d,
            "agree": (dv.agree if dv else None),
            "confidence": conf,
            "reasoning": (dv.reasoning if dv else ""),
        })
    return {
        "agree": verdict.overall_agree,
        "confidence": _clamp(verdict.overall_confidence),
        "damage_confidences": damage_confidences,
        "damage_verdicts": damage_verdicts,
        "reasoning": verdict.overall_reasoning,
        "evidence_images": evidence_images,
        "comment_corroboration": comment_id,
    }


def build_geometry_images(
    estimate: dict[str, Any],
    panel_evidence: dict[str, dict[str, list[str]]],
    panel_verdicts: dict[str, PanelVisionVerdict | None],
    panel_to_claim: dict[str, dict[str, Any]],
    overlay_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    # per (panel, image) -> PanelImageVerdict
    image_lookup: dict[tuple[str, str], PanelImageVerdict] = {}
    for panel, verdict in panel_verdicts.items():
        if not verdict:
            continue
        for iv in verdict.per_image:
            image_lookup[(panel, iv.image_name)] = iv

    out = []
    for image in extract_geometry_images(estimate):
        iname = image.get("image_name")
        assessment = []
        for part in image.get("geometry_damage_parts", []) or []:
            pname = part.get("name")
            if not pname or pname == "Unknown":
                continue
            dts = sorted({d.get("damage_type") for d in part.get("damages", []) or [] if d.get("damage_type")})
            iv = image_lookup.get((pname, iname))
            corr = panel_to_claim.get(_norm(pname))
            assessment.append({
                "panel": pname,
                "damage_types": dts,
                "agree": (iv.agree if iv else None),
                "confidence": (_clamp(iv.confidence) if iv else None),
                "reasoning": (iv.reasoning if iv else ""),
                "from_comment": corr["claim_id"] if corr else None,
            })
        out.append({
            "image_name": iname,
            "overlay_image_ref": overlay_lookup.get(iname or ""),
            "image_size": image.get("image_size"),
            "vehicle_view_type": image.get("vehicle_view_type"),
            "geometry_damage_parts": image.get("geometry_damage_parts", []),
            "requires_review": image.get("requires_review", {}),
            "damage_assessment": assessment,
        })
    return out


# --------------------------------------------------------------------------- #
# aggregation + report text
# --------------------------------------------------------------------------- #
def build_stats(damaged_panels: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"panels": len(damaged_panels), "damage_units": 0,
              "agreed": 0, "disagreed": 0, "low_confidence": 0, "not_evaluated": 0}
    for p in damaged_panels:
        for dv in p["claude_verdict"]["damage_verdicts"]:
            counts["damage_units"] += 1
            if dv["agree"] is None:
                counts["not_evaluated"] += 1
                continue
            if dv["agree"]:
                counts["agreed"] += 1
            else:
                counts["disagreed"] += 1
            if dv["confidence"] is not None and dv["confidence"] < LOW_CONF:
                counts["low_confidence"] += 1
    return counts


def build_overall_status(damaged_panels: list[dict[str, Any]], decider: str) -> str:
    if decider != "vision":
        return "needs_human_review"
    any_unevaluated = any(
        dv["agree"] is None
        for p in damaged_panels for dv in p["claude_verdict"]["damage_verdicts"]
    )
    any_disagree = any(
        dv["agree"] is False
        for p in damaged_panels for dv in p["claude_verdict"]["damage_verdicts"]
    )
    if any_unevaluated:
        return "needs_human_review"
    if any_disagree:
        return "partially_verified"
    return "all_verified"


def build_headline(overall_status: str, stats: dict[str, int]) -> str:
    if overall_status == "all_verified":
        return f"검출된 외판 파손 {stats['damage_units']}건이 모두 Claude Vision 검증에 동의되었습니다."
    if overall_status == "partially_verified":
        return (f"외판 파손 {stats['damage_units']}건 중 {stats['disagreed']}건은 Vision이 동의하지 않았습니다 "
                f"(저신뢰 {stats['low_confidence']}건).")
    return "일부 파손을 자동 검증하지 못해 사람 검토가 필요합니다."


def build_narrative(
    comment: str | None,
    meta: dict[str, Any],
    damaged_panels: list[dict[str, Any]],
    stats: dict[str, int],
    decider: str,
    overall_status: str,
) -> str:
    vehicle = (meta.get("vehicle_info", {}) or {}).get("vehicle_no") or "차량번호 미상"
    lines = [f"[차량] {vehicle}", f"[접수 코멘트] {comment or '(없음)'}"]
    engine = "Claude Vision 검증" if decider == "vision" else "규칙 기반(Vision 미수행)"
    lines.append(
        f"[파손 전수 검증] {engine} — 파손 {stats['panels']}개 패널 / {stats['damage_units']}개 손상유형, "
        f"동의 {stats['agreed']}, 비동의 {stats['disagreed']}, 저신뢰 {stats['low_confidence']}, "
        f"미검증 {stats['not_evaluated']}."
    )
    for p in damaged_panels:
        cv = p["claude_verdict"]
        parts = []
        for dv in cv["damage_verdicts"]:
            if dv["agree"] is None:
                parts.append(f"{dv['damage_type']}(미검증)")
            else:
                mark = "동의" if dv["agree"] else "비동의"
                parts.append(f"{dv['damage_type']}({dv['confidence']:.2f},{mark})")
        tag = f" [코멘트 보강: {cv['comment_corroboration']}]" if cv["comment_corroboration"] else ""
        lines.append(f"  · {p['name']}: " + ", ".join(parts) + tag)

    if overall_status == "all_verified":
        lines.append("[결론] 모든 검출 파손이 Vision 검증에 동의되어 본 결과로 견적서 작성이 가능합니다.")
    elif overall_status == "partially_verified":
        lines.append("[결론] 비동의/저신뢰 손상 항목을 확인한 뒤 견적을 확정하세요.")
    else:
        lines.append("[결론] 자동 검증하지 못한 항목이 있어 담당자 검토가 필요합니다.")
    return "\n".join(lines)
