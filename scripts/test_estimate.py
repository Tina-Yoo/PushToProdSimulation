#!/usr/bin/env python3
"""Call the skrentalcar exterior-damage estimate API and summarize the result.

POST /api/v1/skrentalcar/exterior-damage/estimate (multipart, SSE).

The complete event carries ``request_id``, ``meta`` (vehicle_info,
damaged_panels, estimated_repair_cost, geometry_info, ...) and ``images``
(vis_* groups of base64 visualizations).

Usage:
    export SKR_ACCESS_TOKEN=...
    python scripts/test_estimate.py scripts/sample --detail --json-out scripts/out/result.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from skr_common import (
    DEFAULT_URL,
    ESTIMATE_PATH,
    build_image_parts,
    collect_images,
    dump_result_json,
    post_sse_collect,
    resolve_token,
    save_vis_images,
)


def run_estimate(
    images: List[Path],
    token: str,
    *,
    url: str = DEFAULT_URL,
    request_id: Optional[str] = None,
    vehicle_category: Optional[str] = None,
    match_hints: Optional[str] = None,
    return_detail_visualization: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """Run damage estimation and return the complete-event payload.

    Pass ``request_id`` from a prior slot-cls run so the server reuses its
    classification cache instead of re-running it.
    """
    data: Dict[str, str] = {
        "return_detail_visualization": "true" if return_detail_visualization else "false",
    }
    if request_id:
        data["request_id"] = request_id
    if vehicle_category:
        data["vehicle_category"] = vehicle_category
    if match_hints:
        data["match_hints"] = match_hints

    return post_sse_collect(
        url.rstrip("/") + ESTIMATE_PATH,
        token,
        files=build_image_parts(images),
        data=data,
        verbose=verbose,
    )


def print_summary(result: Dict[str, Any]) -> None:
    """Print a human-readable summary of an estimate result."""
    meta = result.get("meta", {}) if isinstance(result, dict) else {}
    print(f"request_id : {result.get('request_id')}")

    vinfo = meta.get("vehicle_info") or {}
    if vinfo:
        print(f"vehicle    : {vinfo.get('vehicle_category')} / {vinfo.get('vehicle_no')}")
    print(f"images     : total={meta.get('total_images')} non_vehicle={meta.get('non_vehicle')}")

    panels = meta.get("damaged_panels") or []
    print(f"damaged panels ({len(panels)}):")
    for p in panels:
        if not isinstance(p, dict):
            continue
        print(
            f"  - {p.get('name')}: damages={p.get('damages')} "
            f"repair_types={p.get('repair_types')}"
        )

    cost = meta.get("estimated_repair_cost") or {}
    if cost:
        print("estimated repair cost:")
        print(f"  polishing  panels={cost.get('required_polishing_panels')}")
        print(f"  repainting panels={cost.get('required_repainting_panels')}")
        print(f"  repair     panels={cost.get('required_repair_panels')}")
        print(f"  TOTAL      = {cost.get('total_repair_cost')}")

    geom = (meta.get("geometry_info") or {}).get("geometry_images") or []
    print(f"geometry images: {len(geom)}")

    images = result.get("images") or {}
    if images:
        counts = {g: len(v) for g, v in images.items() if isinstance(v, list)}
        print(f"visualization images: {counts}")

    if meta.get("error_msg") and meta.get("error_msg") != "pass":
        print(f"error_msg  : {meta.get('error_msg')}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="skrentalcar estimate test")
    parser.add_argument("folder", type=Path, help="folder of images (searched recursively)")
    parser.add_argument("--url", default=DEFAULT_URL, help="server base URL")
    parser.add_argument("--token", default=None, help="access_token (or set SKR_ACCESS_TOKEN)")
    parser.add_argument("--request-id", default=None, help="reuse a slot-cls request_id")
    parser.add_argument("--vehicle-category", default=None, help="vehicle category")
    parser.add_argument("--detail", action="store_true", help="return_detail_visualization=true")
    parser.add_argument("--out-dir", type=Path, default=None, help="save vis_* images here")
    parser.add_argument("--json-out", type=Path, default=None, help="save full estimate JSON here")
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
    result = run_estimate(
        images, token, url=args.url,
        request_id=args.request_id, vehicle_category=args.vehicle_category,
        return_detail_visualization=args.detail, verbose=args.verbose,
    )
    print_summary(result)

    if args.out_dir:
        n = save_vis_images(result.get("images", {}), args.out_dir)
        print(f"\nSaved {n} visualization image(s) to {args.out_dir}")
    if args.json_out:
        dump_result_json(result, args.json_out)
        print(f"Saved full estimate JSON to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
