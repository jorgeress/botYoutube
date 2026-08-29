"""
PIL-based renderer for data_frame beats, skips ComfyUI entirely.

A data_frame beat contains pure data visualization (bar charts, diagrams)
with no stickman character. These are rendered deterministically with PIL
using the style palette: ComfyUI is never called for them.

Used by:
  _comfyui.py: routes data_frame beats here before the ComfyUI loop
  parse_script.py: classify_beat_type() calls is_data_frame()
  generate_image_prompts.py: sets image_prompt="" for data_frame beats
"""

from __future__ import annotations
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont
from config import STYLE_PALETTE, FONT_PATHS_BOLD, FONT_PATHS_REGULAR


# ── Detection ──────────────────────────────────────────────────────────────────

_CHART_KW = [
    "bar chart", "bar graph", "chart showing", "graph showing",
    "line graph", "pie chart", "chart with bars", "rising bars",
    "bars of increasing", "bars increasing", "concept diagram",
    "arrow diagram", "flow diagram", "chart with",
]
_CHAR_KW = [
    "stickman", "stick figure", "figure ", "person ", "character ",
    "scientist", "researcher", "teacher", "doctor", "child ",
    " human", " man ", " woman ", "people",
]


def is_data_frame(visual: str) -> bool:
    """True when the visual is pure data (chart/diagram) with no character."""
    v = visual.lower()
    has_chart = any(k in v for k in _CHART_KW)
    has_char  = any(k in v for k in _CHAR_KW)
    return has_chart and not has_char


# ── Font helpers ───────────────────────────────────────────────────────────────

def _load_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = FONT_PATHS_BOLD if bold else FONT_PATHS_REGULAR
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _measure(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


# ── Full-frame renderers ───────────────────────────────────────────────────────

def _render_full_chart(draw: ImageDraw.Draw, img: Image.Image,
                       chart: dict) -> None:
    """Draw a centered full-frame bar chart using the full canvas width."""
    pal  = STYLE_PALETTE
    w, h = img.size
    bars = chart.get("bars", [])
    title = chart.get("title", "")
    if not bars:
        return

    n        = len(bars)
    cx0      = int(w * 0.10)
    cx1      = int(w * 0.90)
    cy0      = int(h * 0.18)
    cy1      = int(h * 0.76)
    chart_w  = cx1 - cx0
    chart_h  = cy1 - cy0

    bar_gap = int(chart_w * 0.06)
    bar_w   = (chart_w - bar_gap * (n + 1)) // n
    colors  = [
        (70, 130, 200), (240, 150, 50), (80, 180, 80),
        (200, 70, 70),  (150, 100, 200),
    ]

    label_font = _load_font(min(int(h * 0.048), 30), bold=False)
    val_font   = _load_font(min(int(h * 0.042), 26), bold=True)

    for i, (label, rel_h) in enumerate(bars):
        rel_h = max(0.1, min(1.0, float(rel_h)))
        bx0 = cx0 + bar_gap + i * (bar_w + bar_gap)
        bx1 = bx0 + bar_w
        by0 = cy0 + int(chart_h * (1.0 - rel_h))
        by1 = cy1

        color = colors[i % len(colors)]
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=6, fill=color)
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=6,
                                outline=(40, 40, 40), width=2)

        # Value label above bar
        pct_text = f"{int(rel_h * 100)}%"
        vw, vh = _measure(draw, pct_text, val_font)
        draw.text((bx0 + (bar_w - vw) // 2, by0 - vh - 8),
                  pct_text, font=val_font, fill=pal["chart_label"])

        # Category label below bar
        lw, lh = _measure(draw, label, label_font)
        draw.text((bx0 + (bar_w - lw) // 2, by1 + 8),
                  label, font=label_font, fill=pal["chart_label"])

    # Baseline
    draw.rectangle([cx0, cy1, cx1, cy1 + 4], fill=pal["timeline_bar"])

    # Title
    if title:
        tf = _load_font(min(int(h * 0.055), 36), bold=True)
        tw, _ = _measure(draw, title, tf)
        draw.text(((w - tw) // 2, int(h * 0.07)), title,
                  font=tf, fill=pal["chart_title"])


def _render_full_stat(draw: ImageDraw.Draw, img: Image.Image, stat: str) -> None:
    """Draw a large centered stat value (e.g. '40%') on the canvas."""
    pal  = STYLE_PALETTE
    w, h = img.size
    font_size = min(int(h * 0.30), 220)
    font = _load_font(font_size, bold=True)
    tw, th = _measure(draw, stat, font)
    x = (w - tw) // 2
    y = int(h * 0.25)
    # Shadow
    draw.text((x + 5, y + 5), stat, font=font, fill=pal["frame_shadow"])
    # Main
    draw.text((x, y), stat, font=font, fill=pal["frame_fg"])


def _render_fallback_text(draw: ImageDraw.Draw, img: Image.Image,
                          text: str) -> None:
    """Render visual description text when no chart data is available."""
    pal  = STYLE_PALETTE
    w, h = img.size
    text = text[:60].upper()
    font = _load_font(40, bold=True)
    for font_size in range(120, 38, -6):
        font = _load_font(font_size, bold=True)
        tw, th = _measure(draw, text, font)
        if tw <= w * 0.80:
            break
    tw, th = _measure(draw, text, font)
    draw.text(((w - tw) // 2 + 4, int(h * 0.35) + 4), text,
              font=font, fill=pal["frame_shadow"])
    draw.text(((w - tw) // 2,     int(h * 0.35)),      text,
              font=font, fill=pal["frame_fg"])


# ── Public entry point ─────────────────────────────────────────────────────────

def render_data_frame(entry: dict, output_path: str,
                      width: int = 1920, height: int = 1080) -> None:
    """
    Render a full-frame data visualization image for a data_frame beat.
    Reads entry["_overlay"] for chart / stat data built by generate_image_prompts.
    """
    pal  = STYLE_PALETTE
    img  = Image.new("RGB", (width, height), pal["frame_bg"])
    draw = ImageDraw.Draw(img)

    meta = entry.get("_overlay", {})

    if meta.get("chart"):
        _render_full_chart(draw, img, meta["chart"])
    elif meta.get("stat"):
        _render_full_stat(draw, img, meta["stat"])
    else:
        _render_fallback_text(draw, img, entry.get("visual", "DATA"))

    img.save(output_path)
