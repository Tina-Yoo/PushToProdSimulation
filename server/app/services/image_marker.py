from __future__ import annotations

import base64
import io
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from app.config import settings
from app.schemas.marked_image import (
    DamageSectionInput,
    MarkedImageRequest,
    MarkedImageResponse,
    MarkerInfo,
)

# ---------------------------------------------------------------------------
# Panel coordinate map
# Image orientation:
#   x 0% = front,   x 100% = rear
#   y 0% = top,     y 100% = bottom
#   top  = passenger side (조수석)
#   bottom = driver side (운전석)
# ---------------------------------------------------------------------------

# (x_percent, y_percent) = centre of each panel region
PANEL_COORDS: dict[str, Tuple[float, float]] = {
    # ── Centre-line ──────────────────────────────────────────────────────
    "Front-bumper":        (4.8,  50.0),
    "Grille":              (9.0,  50.0),
    "Hood":                (20.0, 50.0),
    "Windshield":          (29.0, 50.0),
    "Roof":                (50.0, 50.0),
    "Back-windshield":     (71.0, 50.0),
    "Trunk":               (87.0, 50.0),
    "Back-bumper":         (95.2, 50.0),
    "License-plate":       (92.0, 57.0),

    # ── Passenger side (조수석 / right / top, y ≈ 20 %) ────────────────
    "Headlight-right":     (7.5,  21.0),
    "Fender-right":        (17.0, 20.0),
    "Front-wheel-right":   (23.0, 13.5),
    "Mirror-right":        (29.5, 19.0),
    "Front-window-right":  (35.0, 21.5),
    "Front-door-right":    (45.0, 22.0),
    "Back-door-right":     (63.0, 22.0),
    "Back-window-right":   (71.5, 21.5),
    "Quarter-panel-right": (78.5, 18.5),
    "Rocker-panel-right":  (50.0, 15.5),
    "Back-wheel-right":    (67.0, 13.5),
    "Tail-light-right":    (83.5, 21.0),

    # ── Driver side (운전석 / left / bottom, y ≈ 80 %) ──────────────────
    "Headlight-left":      (7.5,  79.0),
    "Fender-left":         (17.0, 80.0),
    "Front-wheel-left":    (23.0, 86.5),
    "Mirror-left":         (29.5, 81.0),
    "Front-window-left":   (35.0, 78.5),
    "Front-door-left":     (45.0, 78.0),
    "Back-door-left":      (63.0, 81.5),
    "Back-window-left":    (71.5, 78.5),
    "Quarter-panel-left":  (78.5, 81.5),
    "Rocker-panel-left":   (50.0, 84.5),
    "Back-wheel-left":     (67.0, 86.5),
    "Tail-light-left":     (83.5, 79.0),
}

# (width_pct, height_pct) of the overlay rectangle relative to image size
PANEL_SIZE: dict[str, Tuple[float, float]] = {
    "Front-bumper":        (8.0,  22.0),
    "Back-bumper":         (8.0,  22.0),
    "Hood":                (18.0, 32.0),
    "Trunk":               (14.0, 28.0),
    "Roof":                (20.0, 32.0),
    "Windshield":          (9.0,  26.0),
    "Back-windshield":     (8.0,  24.0),
    "Grille":              (5.0,  14.0),
    "License-plate":       (3.5,   6.0),
    "Front-door-right":    (14.0, 18.0),
    "Front-door-left":     (14.0, 18.0),
    "Back-door-right":     (14.0, 18.0),
    "Back-door-left":      (14.0, 18.0),
    "Fender-right":        (10.0, 16.0),
    "Fender-left":         (10.0, 16.0),
    "Quarter-panel-right": (9.0,  16.0),
    "Quarter-panel-left":  (9.0,  16.0),
    "Rocker-panel-right":  (24.0,  6.0),
    "Rocker-panel-left":   (24.0,  6.0),
    "Mirror-right":        (3.5,   5.5),
    "Mirror-left":         (3.5,   5.5),
    "Headlight-right":     (5.0,   9.0),
    "Headlight-left":      (5.0,   9.0),
    "Tail-light-right":    (5.0,   9.0),
    "Tail-light-left":     (5.0,   9.0),
    "Front-wheel-right":   (5.5,   9.0),
    "Front-wheel-left":    (5.5,   9.0),
    "Back-wheel-right":    (5.5,   9.0),
    "Back-wheel-left":     (5.5,   9.0),
    "Front-window-right":  (7.0,   8.0),
    "Front-window-left":   (7.0,   8.0),
    "Back-window-right":   (6.5,   8.0),
    "Back-window-left":    (6.5,   8.0),
}

_DEFAULT_SIZE = (8.0, 12.0)

# RGBA overlay colours
_COLOR_INCLUDED   = (220,  50,  50, 140)   # red
_COLOR_REVIEW     = (240, 140,  30, 140)   # orange
_COLOR_EXCLUDED   = (150, 150, 150, 120)   # gray

# Text
_TEXT_FILL    = (255, 255, 255, 255)
_TEXT_OUTLINE = (30,  30,  30,  220)

# Font search paths (Windows / Linux)
_FONT_CANDIDATES = [
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def _overlay_color(section: DamageSectionInput) -> Tuple[int, int, int, int]:
    if not section.included_in_estimate:
        return _COLOR_EXCLUDED
    if section.requires_review:
        return _COLOR_REVIEW
    return _COLOR_INCLUDED


def _status(section: DamageSectionInput) -> str:
    if not section.included_in_estimate:
        return "excluded"
    if section.requires_review:
        return "needs_review"
    return "included"


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    offsets = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for dx, dy in offsets:
        draw.text((x + dx, y + dy), text, font=font, fill=_TEXT_OUTLINE, anchor="mm")
    draw.text((x, y), text, font=font, fill=_TEXT_FILL, anchor="mm")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_marked_image(request: MarkedImageRequest) -> MarkedImageResponse:
    img_path = settings.resources_dir / "cardefault.jpg"
    base = Image.open(img_path).convert("RGBA")
    W, H = base.size

    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Font size: ~6% of image height, min 14px
    font_size = max(14, int(H * 0.06))
    font = _load_font(font_size)

    markers: List[MarkerInfo] = []
    marker_no = 0

    for section in request.damage_sections:
        panel = section.panel
        if not panel or panel not in PANEL_COORDS:
            continue

        cx_pct, cy_pct = PANEL_COORDS[panel]
        w_pct, h_pct = PANEL_SIZE.get(panel, _DEFAULT_SIZE)

        cx = W * cx_pct / 100
        cy = H * cy_pct / 100
        half_w = W * w_pct / 200
        half_h = H * h_pct / 200

        x0 = max(0.0, cx - half_w)
        y0 = max(0.0, cy - half_h)
        x1 = min(float(W), cx + half_w)
        y1 = min(float(H), cy + half_h)

        draw.rectangle([(x0, y0), (x1, y1)], fill=_overlay_color(section))

        marker_no += 1
        _draw_outlined_text(draw, cx, cy, str(marker_no), font)

        markers.append(
            MarkerInfo(
                marker_no=marker_no,
                damage_item_id=section.damage_item_id,
                panel=panel,
                panel_label=section.panel_label,
                damage_type_labels=section.damage_type_labels,
                confidence_percent=section.confidence_percent,
                requires_review=section.requires_review,
                included_in_estimate=section.included_in_estimate,
                status=_status(section),
                x_percent=cx_pct,
                y_percent=cy_pct,
            )
        )

    result = Image.alpha_composite(base, overlay).convert("RGB")

    buf = io.BytesIO()
    result.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    estimate_id = request.estimate_id or "unknown"
    filename = f"{estimate_id}_marked_damage_summary.png"

    return MarkedImageResponse(
        filename=filename,
        content_type="image/png",
        data=b64,
        marker_count=len(markers),
        markers=markers,
    )
