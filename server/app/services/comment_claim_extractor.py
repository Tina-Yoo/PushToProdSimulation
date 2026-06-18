from __future__ import annotations

import json
import re
from typing import Optional

import anthropic

from app.config import settings
from app.schemas.comment_claims import ClaimItem, CommentClaimsRequest, CommentClaimsResponse

# ---------------------------------------------------------------------------
# Allowed code sets (loaded once from estimate_type.json)
# ---------------------------------------------------------------------------

with open(settings.resources_dir / "estimate_type.json", encoding="utf-8") as _f:
    _ESTIMATE_TYPE = json.load(_f)

ALLOWED_PANELS: set[str] = set(_ESTIMATE_TYPE["panels"])
ALLOWED_DAMAGE_TYPES: set[str] = set(_ESTIMATE_TYPE["damage_types"])
ALLOWED_SIDES: set[str] = set(_ESTIMATE_TYPE["sides"])
ALLOWED_AREAS: set[str] = set(_ESTIMATE_TYPE["areas"])
ALLOWED_SEVERITIES: set[str] = set(_ESTIMATE_TYPE["severities"])

# ---------------------------------------------------------------------------
# Normalization aliases
# ---------------------------------------------------------------------------

_PANEL_ALIASES: dict[str, str] = {
    "back bumper": "Back-bumper",
    "back_bumper": "Back-bumper",
    "rear bumper": "Back-bumper",
    "rear_bumper": "Back-bumper",
    "뒷범퍼": "Back-bumper",
    "후범퍼": "Back-bumper",
    "front bumper": "Front-bumper",
    "front_bumper": "Front-bumper",
    "앞범퍼": "Front-bumper",
    "전범퍼": "Front-bumper",
    "back door left": "Back-door-left",
    "back_door_left": "Back-door-left",
    "rear door left": "Back-door-left",
    "back door right": "Back-door-right",
    "back_door_right": "Back-door-right",
    "rear door right": "Back-door-right",
    "front door left": "Front-door-left",
    "front_door_left": "Front-door-left",
    "front door right": "Front-door-right",
    "front_door_right": "Front-door-right",
    "hood": "Hood",
    "후드": "Hood",
    "trunk": "Trunk",
    "트렁크": "Trunk",
    "roof": "Roof",
    "지붕": "Roof",
    "windshield": "Windshield",
    "앞유리": "Windshield",
    "fender left": "Fender-left",
    "fender_left": "Fender-left",
    "fender right": "Fender-right",
    "fender_right": "Fender-right",
    "mirror left": "Mirror-left",
    "mirror_left": "Mirror-left",
    "mirror right": "Mirror-right",
    "mirror_right": "Mirror-right",
    "grille": "Grille",
    "그릴": "Grille",
    "license plate": "License-plate",
    "license_plate": "License-plate",
    "번호판": "License-plate",
}

_DAMAGE_ALIASES: dict[str, str] = {
    "deep scratch": "DeepScratched",
    "deep_scratch": "DeepScratched",
    "deep scratched": "DeepScratched",
    "깊은 스크래치": "DeepScratched",
    "깊은스크래치": "DeepScratched",
    "micro scratch": "MicroScratched",
    "micro_scratch": "MicroScratched",
    "micro scratched": "MicroScratched",
    "마이크로 스크래치": "MicroScratched",
    "scratch": "Scratched",
    "scratched": "Scratched",
    "스크래치": "Scratched",
    "touchup paint": "TouchupPaint",
    "touchup_paint": "TouchupPaint",
    "터치업": "TouchupPaint",
    "crush": "Crushed",
    "dent": "Crushed",
    "dented": "Crushed",
    "찌그러짐": "Crushed",
    "찌그러든": "Crushed",
    "crack": "Crack",
    "균열": "Crack",
    "rust surface": "RustSurface",
    "rust_surface": "RustSurface",
    "녹": "RustSurface",
    "rust deep": "RustDeep",
    "rust_deep": "RustDeep",
    "깊은 녹": "RustDeep",
    "mud splash": "MudSplash",
    "mud_splash": "MudSplash",
    "흙탕물": "MudSplash",
    "tire damage": "TireDamage",
    "tire_damage": "TireDamage",
    "타이어": "TireDamage",
    "break": "Breakage",
    "파손": "Breakage",
    "stain": "Stain",
    "얼룩": "Stain",
    "chip": "Chip",
    "칩": "Chip",
    "swirl": "Swirl",
    "소용돌이": "Swirl",
    "separated": "Separated",
    "분리": "Separated",
    "떨어짐": "Separated",
    "marker": "Marker",
    "마커": "Marker",
}


def _normalize(value: Optional[str], allowed: set[str], aliases: dict[str, str]) -> Optional[str]:
    if not value:
        return None
    if value in allowed:
        return value
    # Case-insensitive exact match
    lower = value.lower()
    for code in allowed:
        if code.lower() == lower:
            return code
    # Hyphen/underscore/space normalisation
    normalised = lower.replace("_", "-").replace(" ", "-")
    for code in allowed:
        if code.lower().replace("_", "-").replace(" ", "-") == normalised:
            return code
    # Alias lookup
    return aliases.get(lower)


def normalize_panel(value: Optional[str]) -> Optional[str]:
    return _normalize(value, ALLOWED_PANELS, _PANEL_ALIASES)


def normalize_damage_type(value: Optional[str]) -> Optional[str]:
    return _normalize(value, ALLOWED_DAMAGE_TYPES, _DAMAGE_ALIASES)


def normalize_side(value: Optional[str]) -> Optional[str]:
    return _normalize(value, ALLOWED_SIDES, {})


def normalize_area(value: Optional[str]) -> Optional[str]:
    return _normalize(value, ALLOWED_AREAS, {})


def normalize_severity(value: Optional[str]) -> Optional[str]:
    return _normalize(value, ALLOWED_SEVERITIES, {})


# ---------------------------------------------------------------------------
# Claude LLM extraction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a vehicle damage claim extractor. "
    "Given a user comment about vehicle damage (possibly in Korean), "
    "extract each distinct damage as a separate claim.\n\n"
    "Return ONLY a valid JSON array — no markdown, no explanation. Each element:\n"
    '{{\n'
    '  "side": "<driver|passenger|left|right|front|rear|null>",\n'
    '  "area": "<front|rear|side|roof|underbody|null>",\n'
    '  "panel": "<panel code or null>",\n'
    '  "damage_type": "<damage type code or null>",\n'
    '  "severity": "<low|moderate|high|null>",\n'
    '  "raw_text": "<relevant excerpt from original comment>",\n'
    '  "confidence": <0.0-1.0>\n'
    "}}\n\n"
    "Allowed panel codes: {panels}\n\n"
    "Allowed damage_type codes: {damage_types}"
)


async def _claude_extract(comment: str, model: str) -> list[dict]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    system = _SYSTEM_PROMPT.format(
        panels=", ".join(sorted(ALLOWED_PANELS)),
        damage_types=", ".join(sorted(ALLOWED_DAMAGE_TYPES)),
    )

    response = await client.messages.create(
        model=model,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": comment}],
    )

    text = response.content[0].text.strip()
    # Strip markdown code fence if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------

_SIDE_KW: list[tuple[str, str]] = [
    ("조수석", "passenger"),
    ("passenger", "passenger"),
    ("운전석", "driver"),
    ("driver", "driver"),
    ("좌측", "left"),
    ("우측", "right"),
]

_AREA_KW: list[tuple[str, str]] = [
    ("앞범퍼", "front"),
    ("뒷범퍼", "rear"),
    ("전면", "front"),
    ("후면", "rear"),
    ("front", "front"),
    ("rear", "rear"),
    ("back", "rear"),
    ("앞", "front"),
    ("뒷", "rear"),  # compound syllable — must come before bare "뒤"
    ("뒤", "rear"),
    ("측면", "side"),
    ("지붕", "roof"),
    ("roof", "roof"),
    ("하부", "underbody"),
]

# (required_area, required_side, keyword_in_text) -> panel_code
# More specific rules first
_PANEL_RULES: list[tuple[Optional[str], Optional[str], str, str]] = [
    (None, None, "뒷범퍼", "Back-bumper"),
    (None, None, "앞범퍼", "Front-bumper"),
    ("rear", None, "범퍼", "Back-bumper"),
    ("rear", None, "bumper", "Back-bumper"),
    ("front", None, "범퍼", "Front-bumper"),
    ("front", None, "bumper", "Front-bumper"),
    # Direct compound-syllable door rules — no area context required
    (None, "driver", "뒷문", "Back-door-left"),
    (None, "passenger", "뒷문", "Back-door-right"),
    (None, "driver", "앞문", "Front-door-left"),
    (None, "passenger", "앞문", "Front-door-right"),
    ("rear", "driver", "문", "Back-door-left"),
    ("rear", "driver", "door", "Back-door-left"),
    ("rear", "passenger", "문", "Back-door-right"),
    ("rear", "passenger", "door", "Back-door-right"),
    ("front", "driver", "문", "Front-door-left"),
    ("front", "driver", "door", "Front-door-left"),
    ("front", "passenger", "문", "Front-door-right"),
    ("front", "passenger", "door", "Front-door-right"),
    (None, None, "후드", "Hood"),
    (None, None, "hood", "Hood"),
    (None, None, "트렁크", "Trunk"),
    (None, None, "trunk", "Trunk"),
    (None, None, "앞유리", "Windshield"),
    (None, None, "windshield", "Windshield"),
    (None, None, "지붕", "Roof"),
    (None, None, "roof", "Roof"),
    (None, None, "그릴", "Grille"),
    (None, None, "grille", "Grille"),
    (None, None, "번호판", "License-plate"),
    (None, "driver", "휀더", "Fender-left"),
    (None, "passenger", "휀더", "Fender-right"),
    (None, "driver", "fender", "Fender-left"),
    (None, "passenger", "fender", "Fender-right"),
    (None, "driver", "미러", "Mirror-left"),
    (None, "passenger", "미러", "Mirror-right"),
    (None, "driver", "mirror", "Mirror-left"),
    (None, "passenger", "mirror", "Mirror-right"),
    ("rear", "driver", "휠", "Back-wheel-left"),
    ("rear", "passenger", "휠", "Back-wheel-right"),
    ("front", "driver", "휠", "Front-wheel-left"),
    ("front", "passenger", "휠", "Front-wheel-right"),
    ("rear", "driver", "wheel", "Back-wheel-left"),
    ("rear", "passenger", "wheel", "Back-wheel-right"),
    ("front", "driver", "wheel", "Front-wheel-left"),
    ("front", "passenger", "wheel", "Front-wheel-right"),
    ("rear", "driver", "테일라이트", "Tail-light-left"),
    ("rear", "passenger", "테일라이트", "Tail-light-right"),
    ("rear", "driver", "tail", "Tail-light-left"),
    ("rear", "passenger", "tail", "Tail-light-right"),
    ("front", "driver", "헤드라이트", "Headlight-left"),
    ("front", "passenger", "헤드라이트", "Headlight-right"),
    ("front", "driver", "headlight", "Headlight-left"),
    ("front", "passenger", "headlight", "Headlight-right"),
]

_DAMAGE_KW: list[tuple[str, str]] = [
    ("깊은 스크래치", "DeepScratched"),
    ("깊은스크래치", "DeepScratched"),
    ("deep scratch", "DeepScratched"),
    ("마이크로 스크래치", "MicroScratched"),
    ("micro scratch", "MicroScratched"),
    ("스크래치", "Scratched"),
    ("scratch", "Scratched"),
    ("찌그러짐", "Crushed"),
    ("찌그러든", "Crushed"),
    ("찌그러", "Crushed"),
    ("crush", "Crushed"),
    ("균열", "Crack"),
    ("crack", "Crack"),
    ("파손", "Breakage"),
    ("breakage", "Breakage"),
    ("깊은 녹", "RustDeep"),
    ("녹", "RustSurface"),
    ("rust", "RustSurface"),
    ("흙탕물", "MudSplash"),
    ("mud", "MudSplash"),
    ("얼룩", "Stain"),
    ("stain", "Stain"),
    ("타이어", "TireDamage"),
    ("tire", "TireDamage"),
    ("칩", "Chip"),
    ("chip", "Chip"),
    ("소용돌이", "Swirl"),
    ("swirl", "Swirl"),
    ("분리", "Separated"),
    ("떨어짐", "Separated"),
    ("separated", "Separated"),
    ("터치업", "TouchupPaint"),
    ("touchup", "TouchupPaint"),
    ("마커", "Marker"),
    ("marker", "Marker"),
]

_SEVERITY_KW: list[tuple[str, str]] = [
    ("깊은", "high"),
    ("심한", "high"),
    ("크게", "high"),
    ("큰", "high"),
    ("severe", "high"),
    ("deep", "high"),
    ("경미한", "low"),
    ("가벼운", "low"),
    ("작은", "low"),
    ("slight", "low"),
    ("minor", "low"),
    ("중간", "moderate"),
    ("보통", "moderate"),
    ("moderate", "moderate"),
]

_STRIP_ENDINGS = re.compile(
    r"[이가은는을를]?\s*(?:있고|이고|있으며|있습니다|있어요|입니다|이에요|이다|있었습니다)?\s*[.!?]*\s*$"
)


def _split_comment(comment: str) -> list[str]:
    parts = re.split(r"있고[,，]?\s*|이고[,，]?\s*|있으며[,，]?\s*|[,，]\s*", comment)
    return [p.strip() for p in parts if p.strip()]


def _raw_text(segment: str) -> str:
    cleaned = _STRIP_ENDINGS.sub("", segment).strip()
    return cleaned if cleaned else segment


def _kw_match(text: str, pairs: list[tuple[str, str]]) -> Optional[str]:
    lower = text.lower()
    for kw, value in pairs:
        if kw in lower:
            return value
    return None


def _detect_panel(text: str, side: Optional[str], area: Optional[str]) -> Optional[str]:
    lower = text.lower()
    for rule_area, rule_side, kw, panel_code in _PANEL_RULES:
        if rule_area and area != rule_area:
            continue
        if rule_side and side != rule_side:
            continue
        if kw in lower:
            return panel_code
    return None


def _fallback_extract(comment: str) -> list[ClaimItem]:
    segments = _split_comment(comment)
    claims: list[ClaimItem] = []

    for idx, seg in enumerate(segments, start=1):
        side = _kw_match(seg, _SIDE_KW)
        area = _kw_match(seg, _AREA_KW)
        panel = _detect_panel(seg, side, area)
        damage = _kw_match(seg, _DAMAGE_KW)
        severity = _kw_match(seg, _SEVERITY_KW)

        if panel or damage:
            claims.append(
                ClaimItem(
                    claim_id=f"claim_{idx:03d}",
                    side=side,
                    area=area,
                    panel=panel,
                    damage_type=damage,
                    severity=severity,
                    raw_text=_raw_text(seg),
                    confidence=0.6,
                )
            )

    if not claims:
        claims.append(
            ClaimItem(
                claim_id="claim_001",
                side=None,
                area=None,
                panel=None,
                damage_type=None,
                severity=None,
                raw_text=comment,
                confidence=0.3,
            )
        )

    return claims


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def extract_claims(request: CommentClaimsRequest) -> CommentClaimsResponse:
    model: Optional[str] = settings.claude_model
    llm_error: Optional[str] = None
    extractor: str
    claims: list[ClaimItem]

    if not settings.anthropic_api_key:
        llm_error = "ANTHROPIC_API_KEY is not configured."
        extractor = "local_rule_based_fallback"
        model = None
        claims = _fallback_extract(request.comment)
    else:
        try:
            raw_list = await _claude_extract(request.comment, model)
            claims = [
                ClaimItem(
                    claim_id=f"claim_{i:03d}",
                    side=normalize_side(r.get("side")),
                    area=normalize_area(r.get("area")),
                    panel=normalize_panel(r.get("panel")),
                    damage_type=normalize_damage_type(r.get("damage_type")),
                    severity=normalize_severity(r.get("severity")),
                    raw_text=r.get("raw_text", ""),
                    confidence=float(r.get("confidence", 0.95)),
                )
                for i, r in enumerate(raw_list, start=1)
            ]
            extractor = "claude_claim_extractor"
        except Exception as exc:
            llm_error = str(exc)
            extractor = "local_rule_based_fallback"
            model = None
            claims = _fallback_extract(request.comment)

    return CommentClaimsResponse(
        estimate_id=request.estimate_id,
        comment=request.comment,
        extractor=extractor,
        model=model,
        llm_error=llm_error,
        claims=claims,
    )
