"""
PIL post-processing overlays applied to generated images before clip encoding.

Flux is unreliable for text, numbers, charts, and precise positioning.
This module draws those elements programmatically, guaranteed correct every time.

Called from _comfyui.py after the image is copied to _src.png.
"""

from __future__ import annotations
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont
from config import STYLE_PALETTE, FONT_PATHS_BOLD, FONT_PATHS_REGULAR

# ── Font loading ──────────────────────────────────────────────────────────────
_FONT_BOLD    = FONT_PATHS_BOLD
_FONT_REGULAR = FONT_PATHS_REGULAR

def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    for path in (_FONT_BOLD if bold else _FONT_REGULAR):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _text_size(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def _outlined_text(draw: ImageDraw.Draw, xy: tuple[int, int], text: str,
                   font, fill=(15, 15, 15), outline=(255, 255, 255), stroke=3):
    draw.text(xy, text, font=font, fill=outline,
              stroke_width=stroke, stroke_fill=outline)
    draw.text(xy, text, font=font, fill=fill)


# ── Stat overlay (large number/percentage) ────────────────────────────────────

def draw_stat(img: Image.Image, label: str, centered: bool = False) -> None:
    """Draw a large stat label (e.g. '40%', '1948', '3M') onto the image."""
    pal = STYLE_PALETTE
    w, h = img.size
    draw = ImageDraw.Draw(img)

    size = min(int(h * 0.20), 110)
    font = _font(size, bold=True)
    tw, th = _text_size(draw, label, font)

    if centered:
        x = (w - tw) // 2
        y = int(h * 0.30)
    else:
        # Right side, vertically centered: leaves left side for character
        x = int(w * 0.58)
        y = (h - th) // 2

    _outlined_text(draw, (x, y), label, font,
                   fill=pal["stat_fill"], outline=pal["stat_outline"], stroke=5)


# ── Inline text label (shorter phrase, e.g. object label) ────────────────────

def draw_label(img: Image.Image, text: str, position: str = "bottom") -> None:
    """Draw a short text label directly on the image, no box, just outlined text."""
    pal = STYLE_PALETTE
    w, h = img.size
    draw = ImageDraw.Draw(img)

    size = min(int(h * 0.075), 46)
    font = _font(size, bold=True)
    tw, th = _text_size(draw, text, font)

    if position == "bottom":
        x = (w - tw) // 2
        y = int(h * 0.82)
    elif position == "top":
        x = (w - tw) // 2
        y = int(h * 0.06)
    else:
        x = (w - tw) // 2
        y = (h - th) // 2

    _outlined_text(draw, (x, y), text, font,
                   fill=pal["label_fg"], outline=pal["label_bg"], stroke=4)


# ── Timeline bar ──────────────────────────────────────────────────────────────

def draw_timeline(img: Image.Image, year: str) -> None:
    """Draw a simple horizontal timeline with the given year marked."""
    pal = STYLE_PALETTE
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Timeline bar: sits in the lower quarter
    bar_y   = int(h * 0.80)
    bar_x0  = int(w * 0.10)
    bar_x1  = int(w * 0.90)
    bar_h   = 4

    # Main line
    draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + bar_h],
                   fill=pal["timeline_bar"])

    # Left and right end ticks
    tick_h = 16
    for x in (bar_x0, bar_x1):
        draw.rectangle([x - 2, bar_y - tick_h // 2,
                        x + 2, bar_y + bar_h + tick_h // 2],
                       fill=pal["timeline_bar"])

    # Year marker: 60% along the line (roughly "now" in historical context)
    pin_x = int(bar_x0 + (bar_x1 - bar_x0) * 0.60)
    pin_y_top = bar_y - 36
    # Vertical pin
    draw.rectangle([pin_x - 2, pin_y_top, pin_x + 2, bar_y], fill=pal["timeline_pin"])
    # Diamond tip
    draw.polygon([(pin_x, pin_y_top - 10),
                  (pin_x + 8, pin_y_top),
                  (pin_x, pin_y_top + 8),
                  (pin_x - 8, pin_y_top)], fill=pal["timeline_pin"])

    # Year label above pin
    font = _font(min(int(h * 0.055), 34), bold=True)
    tw, th = _text_size(draw, year, font)
    lx = pin_x - tw // 2
    ly = pin_y_top - th - 14
    _outlined_text(draw, (lx, ly), year, font,
                   fill=pal["timeline_label_fg"], outline=pal["timeline_outline"], stroke=3)


# ── Bar chart ─────────────────────────────────────────────────────────────────

def draw_bar_chart(img: Image.Image, bars: list[tuple[str, float]],
                   title: str = "") -> None:
    """
    Draw a simple bar chart in the right half of the image.
    bars: list of (label, relative_height) where height is 0.0, 1.0
    """
    w, h = img.size
    draw = ImageDraw.Draw(img)

    chart_x0 = int(w * 0.55)
    chart_x1 = int(w * 0.92)
    chart_y0 = int(h * 0.15)
    chart_y1 = int(h * 0.75)
    chart_w  = chart_x1 - chart_x0
    chart_h  = chart_y1 - chart_y0

    n = len(bars)
    bar_gap  = int(chart_w * 0.08)
    bar_w    = (chart_w - bar_gap * (n + 1)) // n
    colors   = [(70, 130, 200), (240, 150, 50), (80, 180, 80),
                (200, 70, 70), (150, 100, 200)]

    label_font = _font(min(int(h * 0.045), 28), bold=False)

    for i, (label, rel_h) in enumerate(bars):
        rel_h = max(0.1, min(1.0, rel_h))
        bx0 = chart_x0 + bar_gap + i * (bar_w + bar_gap)
        bx1 = bx0 + bar_w
        by0 = chart_y0 + int(chart_h * (1.0 - rel_h))
        by1 = chart_y1

        color = colors[i % len(colors)]
        # Bar with slight rounded top
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=4, fill=color)
        # Thin outline
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=4,
                                outline=(40, 40, 40), width=1)

        # Label below bar
        pal = STYLE_PALETTE
        lw, lh = _text_size(draw, label, label_font)
        lx = bx0 + (bar_w - lw) // 2
        ly = by1 + 6
        draw.text((lx, ly), label, font=label_font, fill=pal["chart_label"])

    # Baseline
    draw.rectangle([chart_x0, chart_y1, chart_x1, chart_y1 + 3],
                   fill=STYLE_PALETTE["timeline_bar"])

    # Title
    if title:
        tf = _font(min(int(h * 0.048), 30), bold=True)
        tw, _ = _text_size(draw, title, tf)
        tx = chart_x0 + (chart_w - tw) // 2
        draw.text((tx, chart_y0 - 36), title, font=tf, fill=STYLE_PALETTE["chart_title"])


# ── Keyword label (concept introduction, sync rule 1) ─────────────────────────

def draw_keyword(img: Image.Image, keyword: str,
                 position: str = "lower_center") -> None:
    """Overlay a key term as prominent bold outlined text, no background box."""
    pal = STYLE_PALETTE
    w, h = img.size
    draw = ImageDraw.Draw(img)

    size = min(int(h * 0.11), 70)
    font = _font(size, bold=True)
    tw, th = _text_size(draw, keyword, font)

    if position == "top":
        x = (w - tw) // 2
        y = int(h * 0.07)
    elif position == "center":
        x = (w - tw) // 2
        y = int(h * 0.40)
    else:  # lower_center (default)
        x = (w - tw) // 2
        y = int(h * 0.74)

    _outlined_text(draw, (x, y), keyword, font,
                   fill=pal["label_fg"], outline=pal["label_bg"], stroke=5)


# ── Size / scale contrast (sync rule 4) ───────────────────────────────────────

def draw_size_contrast(img: Image.Image,
                       big_word: str = "BIG",
                       small_word: str = "small") -> None:
    """Draw two words at very different sizes to show scale or importance contrast."""
    pal = STYLE_PALETTE
    w, h = img.size
    draw = ImageDraw.Draw(img)

    # Big word: large font, left side
    big_size = min(int(h * 0.17), 108)
    big_font = _font(big_size, bold=True)
    bw, bh = _text_size(draw, big_word, big_font)
    bx = int(w * 0.10)
    by = int(h * 0.37)
    draw.text((bx + 3, by + 3), big_word, font=big_font, fill=pal["frame_shadow"])
    draw.text((bx, by), big_word, font=big_font, fill=pal["frame_fg"])

    # Small word: small font, right side, vertically centered with big
    sm_size = min(int(h * 0.05), 34)
    sm_font = _font(sm_size, bold=True)
    sw, sh = _text_size(draw, small_word, sm_font)
    sx = int(w * 0.68)
    sy = by + (bh - sh) // 2
    draw.text((sx, sy), small_word, font=sm_font, fill=pal["frame_fg"])


# ── Main entry point ──────────────────────────────────────────────────────────

def apply_overlays(image_path: str, entry: dict) -> None:
    """
    Parse image_prompt and overlay metadata from the entry dict and apply
    any programmatic overlays to the image at image_path (modified in-place).

    entry keys used: image_prompt, _overlay (optional dict set by generate_image_prompts)
    """
    meta = entry.get("_overlay", {})
    if not meta:
        return

    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))

    # Work on a transparent overlay layer, then composite
    # (Allows partial transparency for backgrounds)

    # Convert back to RGB working image for draw operations
    work = img.convert("RGB")

    applied = False

    # Stat number
    stat = meta.get("stat")
    if stat:
        draw_stat(work, stat, centered=meta.get("stat_centered", False))
        applied = True

    # Explicit text label
    label = meta.get("label")
    if label:
        draw_label(work, label, position=meta.get("label_pos", "bottom"))
        applied = True

    # Timeline
    year = meta.get("year")
    if year:
        draw_timeline(work, year)
        applied = True

    # Bar chart
    chart = meta.get("chart")
    if chart:
        draw_bar_chart(work, chart.get("bars", []), chart.get("title", ""))
        applied = True

    # Keyword label (concept introduction)
    keyword = meta.get("keyword")
    if keyword:
        draw_keyword(work, keyword, position=meta.get("keyword_pos", "lower_center"))
        applied = True

    # Size / scale contrast
    if meta.get("size_contrast"):
        draw_size_contrast(
            work,
            big_word=meta.get("size_contrast_big", "BIG"),
            small_word=meta.get("size_contrast_small", "small"),
        )
        applied = True

    if applied:
        work.save(image_path)
