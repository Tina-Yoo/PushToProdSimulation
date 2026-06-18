#!/usr/bin/env python3
"""Call the skrentalcar slot-cls API and report the slot buckets.

POST /api/v1/skrentalcar/exterior-damage/slot-cls (multipart, SSE).

The complete event looks like::

    {"total_images": 12, "front_center": [7], "front_driver": [8],
     "side_left": [], "rear_driver": [1, 2], "rear_center": [3],
     "rear_passenger": [4, 5], "side_right": [], "front_passenger": [6, 9, 11, 10],
     "other": [0], "non_vehicle": [], "request_id": "20260225_143145"}

Usage:
    export SKR_ACCESS_TOKEN=...
    python scripts/test_slot_cls.py scripts/sample
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

from skr_common import (
    DEFAULT_URL,
    SLOT_CLS_PATH,
    build_image_parts,
    collect_images,
    post_sse_collect,
    resolve_token,
)

# Keys in the slot-cls response that are metadata, not image-index buckets.
_NON_BUCKET_KEYS = {"total_images", "request_id", "error_msg", "meta"}


def run_slot_cls(
    images: List[Path],
    token: str,
    *,
    url: str = DEFAULT_URL,
    vehicle_category: str | None = None,
    match_hints: str | None = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run slot classification and return the complete-event payload."""
    data: Dict[str, str] = {}
    if vehicle_category:
        data["vehicle_category"] = vehicle_category
    if match_hints:
        data["match_hints"] = match_hints

    return post_sse_collect(
        url.rstrip("/") + SLOT_CLS_PATH,
        token,
        files=build_image_parts(images),
        data=data,
        verbose=verbose,
    )


def analysis_target_indices(slots: Dict[str, Any]) -> List[int]:
    """Return image indices flagged as analysis targets.

    Analysis targets are every image in any slot bucket except ``non_vehicle``
    (deduplicated, sorted).
    """
    non_vehicle = {i for i in slots.get("non_vehicle", []) if isinstance(i, int)}
    targets: set[int] = set()
    for key, value in slots.items():
        if key in _NON_BUCKET_KEYS or key == "non_vehicle":
            continue
        if isinstance(value, list):
            targets.update(i for i in value if isinstance(i, int))
    return sorted(targets - non_vehicle)


def print_slots(slots: Dict[str, Any]) -> None:
    print(f"request_id : {slots.get('request_id')}")
    print(f"total      : {slots.get('total_images')}")
    for key, value in slots.items():
        if key in _NON_BUCKET_KEYS:
            continue
        if isinstance(value, list):
            print(f"  {key:<16} {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="skrentalcar slot-cls test")
    parser.add_argument("folder", type=Path, help="folder of images (searched recursively)")
    parser.add_argument("--url", default=DEFAULT_URL, help="server base URL")
    parser.add_argument("--token", default=None, help="access_token (or set SKR_ACCESS_TOKEN)")
    parser.add_argument("--vehicle-category", default=None, help="vehicle category")
    parser.add_argument("--limit", type=int, default=0, help="use at most N images (0 = all)")
    parser.add_argument("--verbose", action="store_true", help="print SSE progress events")
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"Not a directory: {args.folder}", file=sys.stderr)
        return 1

    images = collect_images(args.folder)
    if args.limit > 0:
        images = images[: args.limit]
    if not images:
        print(f"No images found in {args.folder}", file=sys.stderr)
        return 1

    token = resolve_token(args.token)
    slots = run_slot_cls(
        images, token, url=args.url,
        vehicle_category=args.vehicle_category, verbose=args.verbose,
    )
    print_slots(slots)
    targets = analysis_target_indices(slots)
    print(f"\nanalysis targets: {len(targets)}/{len(images)} -> {targets}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
