#!/usr/bin/env python3
"""End-to-end skrentalcar pipeline: folder -> slot-cls -> estimate.

Throw a folder of images at slot-cls, keep only the images it flags as
analysis targets (everything except the ``non_vehicle`` bucket), then send
just those to estimate — reusing slot-cls's ``request_id`` so the server skips
re-classifying.

Usage:
    export SKR_ACCESS_TOKEN=...      # or pass --token
    python scripts/test_skr_pipeline.py scripts/sample
    python scripts/test_skr_pipeline.py scripts/sample --detail --out-dir scripts/out
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from skr_common import (
    DEFAULT_URL,
    collect_images,
    dump_result_json,
    resolve_token,
    save_vis_images,
)
from test_estimate import print_summary, run_estimate
from test_slot_cls import analysis_target_indices, run_slot_cls


def main() -> int:
    parser = argparse.ArgumentParser(description="slot-cls -> estimate pipeline")
    parser.add_argument("folder", type=Path, help="folder of images (searched recursively)")
    parser.add_argument("--url", default=DEFAULT_URL, help="server base URL")
    parser.add_argument("--token", default=None, help="access_token (or set SKR_ACCESS_TOKEN)")
    parser.add_argument("--vehicle-category", default=None, help="vehicle category")
    parser.add_argument("--detail", action="store_true", help="return_detail_visualization=true")
    parser.add_argument("--out-dir", type=Path, default=None, help="save vis_* images here")
    parser.add_argument("--json-out", type=Path, default=None, help="save full estimate JSON here")
    parser.add_argument("--limit", type=int, default=0, help="use at most N images (0 = all)")
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

    # --- Step 1: slot-cls -------------------------------------------------
    print(f"[1/2] slot-cls on {len(images)} image(s) ...")
    slots = run_slot_cls(images, token, url=args.url, vehicle_category=args.vehicle_category)
    request_id = slots.get("request_id")
    targets = analysis_target_indices(slots)
    print(f"      non_vehicle dropped: {len(slots.get('non_vehicle', []))}")
    print(f"      analysis targets: {len(targets)}/{len(images)}  request_id={request_id}")
    for idx in targets:
        print(f"        [{idx}] {images[idx].name}")

    if not targets:
        print("No analysis-target images — nothing to estimate.", file=sys.stderr)
        return 1

    # --- Step 2: estimate (forward only the targets, reuse request_id) ----
    target_paths = [images[i] for i in targets]
    print(f"\n[2/2] estimate on {len(target_paths)} target(s) (request_id reuse) ...")
    result = run_estimate(
        target_paths, token, url=args.url,
        request_id=request_id, vehicle_category=args.vehicle_category,
        return_detail_visualization=args.detail,
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
