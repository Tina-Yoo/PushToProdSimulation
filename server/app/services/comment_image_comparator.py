from __future__ import annotations

import re
from typing import Any


# --------------------------------------------------------------------------- #
# Helpers consumed by the Claude Vision check (Handoff §4).
# The full comment/image comparator is upstream; only the pieces the Vision
# audit imports are implemented here, to the behaviour documented in the handoff.
# --------------------------------------------------------------------------- #


def extract_text_content(data: dict[str, Any]) -> str:
    """Concatenate the text blocks of a Claude /v1/messages response."""
    parts: list[str] = []
    for block in data.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if text:
                parts.append(text)
    return "".join(parts)


def extract_json_object(text: str) -> str:
    """Return the first balanced JSON object found in ``text``.

    Tolerates markdown code fences and leading/trailing prose, since Vision is
    asked for JSON-only but models occasionally wrap it.
    """
    if not text:
        return "{}"
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start = text.find("{")
    if start == -1:
        return "{}"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _iter_geometry_images(estimate: dict[str, Any]) -> list[dict[str, Any]]:
    meta = estimate.get("meta", {}) or {}
    geometry_info = meta.get("geometry_info", {}) or {}
    images = geometry_info.get("geometry_images", []) or []
    return [img for img in images if isinstance(img, dict)]


def extract_geometry_images(estimate: dict[str, Any]) -> list[dict[str, Any]]:
    """All geometry images from estimate.meta.geometry_info.geometry_images."""
    return _iter_geometry_images(estimate)


def build_overlay_lookup(estimate: dict[str, Any]) -> dict[str, str]:
    """Map image_name -> damage-overlay image ref, when the estimate carries one."""
    lookup: dict[str, str] = {}
    for image in _iter_geometry_images(estimate):
        name = image.get("image_name")
        ref = image.get("overlay_image_ref") or image.get("damage_overlay_ref")
        if name and ref:
            lookup[name] = ref
    return lookup


def extract_image_identity_tokens(filename: str) -> set[str]:
    """Split a filename into identity tokens for loose base64 matching."""
    if not filename:
        return set()
    stem = filename.rsplit("/", 1)[-1]
    stem = stem.rsplit(".", 1)[0]
    tokens = {t for t in re.split(r"[\s._\-]+", stem) if t}
    tokens.add(stem)
    return tokens
