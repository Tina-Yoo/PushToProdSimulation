#!/usr/bin/env python3
"""Shared helpers for the skrentalcar AI Model Server test scripts.

Auth, image collection, multipart+SSE POST handling, and result I/O — used by
test_slot_cls.py, test_estimate.py, and test_skr_pipeline.py.

Endpoints (AI Model Server, OpenAPI 1.9.0):
  POST /api/v1/skrentalcar/exterior-damage/slot-cls   (multipart, SSE)
  POST /api/v1/skrentalcar/exterior-damage/estimate   (multipart, SSE)

Auth is an `access_token` request header (APIKeyHeader).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

import httpx

# Base server URL. Override with --url or the SKR_BASE_URL env var.
DEFAULT_URL = os.environ.get("SKR_BASE_URL", "http://localhost:8000")

# Endpoint paths (joined onto the base URL).
SLOT_CLS_PATH = "/api/v1/skrentalcar/exterior-damage/slot-cls"
ESTIMATE_PATH = "/api/v1/skrentalcar/exterior-damage/estimate"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

# estimate/slot-cls run vision models; give them a long read budget.
DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=600.0, write=120.0, pool=10.0)


# --------------------------------------------------------------------------- #
# Token / images
# --------------------------------------------------------------------------- #
def resolve_token(token: Optional[str]) -> str:
    """Return the access token from the argument or SKR_ACCESS_TOKEN env var."""
    token = token or os.environ.get("SKR_ACCESS_TOKEN")
    if not token:
        print(
            "No access token. Pass --token or set SKR_ACCESS_TOKEN.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return token


def collect_images(folder: Path) -> List[Path]:
    """Recursively collect image files under ``folder``, sorted by path."""
    return sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def _content_type(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def build_image_parts(paths: Iterable[Path]) -> List[Tuple[str, Tuple[str, bytes, str]]]:
    """Build httpx multipart parts for the repeated ``images`` field."""
    parts: List[Tuple[str, Tuple[str, bytes, str]]] = []
    for p in paths:
        parts.append(("images", (p.name, p.read_bytes(), _content_type(p))))
    return parts


# --------------------------------------------------------------------------- #
# SSE handling
# --------------------------------------------------------------------------- #
def _iter_sse(resp: httpx.Response) -> Iterator[Tuple[str, str]]:
    """Yield (event, data) pairs from a text/event-stream response.

    Handles multi-line ``data:`` fields and a default event name of "message".
    """
    event = "message"
    data_lines: List[str] = []
    for raw in resp.iter_lines():
        line = raw.rstrip("\r")
        if line == "":  # dispatch on blank line
            if data_lines:
                yield event, "\n".join(data_lines)
            event = "message"
            data_lines = []
            continue
        if line.startswith(":"):  # comment / heartbeat
            continue
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:  # flush trailing event with no terminating blank line
        yield event, "\n".join(data_lines)


def _parse_json(data: str) -> Any:
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def post_sse_collect(
    url: str,
    token: str,
    *,
    files: List[Tuple[str, Tuple[str, bytes, str]]],
    data: Dict[str, str],
    timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    verbose: bool = False,
) -> Dict[str, Any]:
    """POST multipart, consume the SSE stream, and return the final result.

    Returns the payload of the ``complete`` event. Raises RuntimeError if the
    stream emits an ``error`` event. Falls back to plain-JSON parsing when the
    server responds with application/json instead of an event stream.
    """
    headers = {"access_token": token, "accept": "text/event-stream"}
    last_complete: Optional[Any] = None
    last_json: Optional[Any] = None

    with httpx.Client(timeout=timeout) as client:
        with client.stream("POST", url, headers=headers, files=files, data=data) as resp:
            if resp.status_code != 200:
                body = resp.read().decode("utf-8", "replace")
                raise RuntimeError(f"HTTP {resp.status_code} from {url}: {body[:500]}")

            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                payload = _parse_json(resp.read().decode("utf-8", "replace"))
                if isinstance(payload, dict):
                    return payload
                raise RuntimeError(f"Unexpected non-SSE response from {url}")

            for event, raw in _iter_sse(resp):
                payload = _parse_json(raw)
                if verbose and event == "progress":
                    msg = payload if isinstance(payload, dict) else raw
                    print(f"      .. progress: {msg}", file=sys.stderr)
                if payload is not None:
                    last_json = payload
                if event == "error":
                    detail = payload if payload is not None else raw
                    raise RuntimeError(f"Server error event: {detail}")
                if event == "complete":
                    last_complete = payload

    result = last_complete if last_complete is not None else last_json
    if not isinstance(result, dict):
        raise RuntimeError(f"No usable 'complete' payload received from {url}")
    return result


# --------------------------------------------------------------------------- #
# Result I/O
# --------------------------------------------------------------------------- #
def save_vis_images(images: Dict[str, Any], out_dir: Path) -> int:
    """Save base64 visualization images to ``out_dir``.

    ``images`` is the estimate response's ``images`` map:
    {group: [{"filename", "content_type", "data"(base64)}, ...]}.
    Files are written as ``<group>__<filename>`` to avoid collisions.
    Returns the number of files written.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for group, items in (images or {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            data = item.get("data")
            filename = item.get("filename") or f"{group}_{saved}.png"
            if not isinstance(data, str) or not data:
                continue
            try:
                blob = base64.b64decode(data)
            except (ValueError, TypeError):
                continue
            (out_dir / f"{group}__{filename}").write_bytes(blob)
            saved += 1
    return saved


def dump_result_json(result: Dict[str, Any], path: Path) -> None:
    """Write the full result dict to ``path`` as UTF-8 JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
