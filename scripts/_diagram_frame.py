"""
PIL-based renderer for diagram beats (shot: diagram).

Eliminates the clipart-style mismatch that occurs when Flux renders diagrams
without a character: without the CHARACTER_ANCHOR, Flux falls back to clean
flat vector icons that look visually inconsistent with the stickman beats.

This renderer uses the same sprite assets as _sprites.py for left/right symbols.
If either symbol has no sprite file, the beat falls back to ComfyUI Flux
(via the Tarea 0 sketch-style patch in build_prompt_from_fields).

Layout (1920x1080):
  15% margin | left symbol | gap | bold arrow | gap | right symbol | 15% margin
  Optional labels in Caveat-Bold below each symbol.

Beat format:
  (shot: diagram | left: brain | right: coin | arrow: right green | bg: plain-white)
  (shot: diagram | left: clock | right: brain | arrow: right blue | labels: 'CUE','HABIT')
"""

from __future__ import annotations
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont
from config import STYLE_PALETTE, FONT_PATHS_BOLD

_SPRITES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "sprites",
)

_ARROW_COLORS: dict[str, tuple[int, int, int]] = {
    "red":    (220, 50,  50),
    "green":  (50,  190, 50),
    "blue":   (50,  130, 220),
    "yellow": (230, 190, 0),
}


def _has_sprite(name: str) -> bool:
    for suffix in ("_a.png", "_b.png", ".png"):
        if os.path.exists(os.path.join(_SPRITES_DIR, f"{name}{suffix}")):
            return True
    return False


def _load_sprite(name: str, target_size: int) -> Image.Image | None:
    for suffix in ("_a.png", "_b.png", ".png"):
        path = os.path.join(_SPRITES_DIR, f"{name}{suffix}")
        if os.path.exists(path):
            img = Image.open(path).convert("RGBA")
            ratio = target_size / max(img.width, img.height)
            new_w = max(1, int(img.width  * ratio))
            new_h = max(1, int(img.height * ratio))
            return img.resize((new_w, new_h), Image.LANCZOS)
    return None


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS_BOLD:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_arrow(draw: ImageDraw.Draw, x1: int, x2: int, y: int,
                color: tuple[int, int, int], thickness: int = 12) -> None:
    draw.line([(x1, y), (x2, y)], fill=color, width=thickness)
    hw = thickness * 2
    draw.polygon([(x2, y), (x2 - hw, y - hw), (x2 - hw, y + hw)], fill=color)


def can_render(fields: dict) -> bool:
    """True only if both left and right symbols have sprite files available."""
    return _has_sprite(fields.get("left", "")) and _has_sprite(fields.get("right", ""))


def render_diagram_frame(fields: dict, output_path: str,
                         width: int = 1920, height: int = 1080) -> None:
    """
    Render a diagram beat with PIL.
    Layout: left symbol → bold colored arrow → right symbol.
    Optional labels: labels: 'LEFT LABEL','RIGHT LABEL' in Caveat-Bold below symbols.
    """
    pal = STYLE_PALETTE

    left_name  = fields.get("left", "")
    right_name = fields.get("right", "")
    arrow_val  = fields.get("arrow", "right red")
    labels_val = fields.get("labels", "")

    arrow_tokens     = arrow_val.split()
    arrow_color_name = arrow_tokens[1] if len(arrow_tokens) > 1 else "red"
    arrow_color      = _ARROW_COLORS.get(arrow_color_name, (220, 50, 50))

    labels = [l.strip().strip("'\"").upper() for l in labels_val.split(",") if l.strip()] if labels_val else []

    img = Image.new("RGB", (width, height), pal.get("frame_bg", (255, 255, 255)))

    # Symbol size: fit within 22% of height
    sym_size = int(height * 0.22)

    left_sprite  = _load_sprite(left_name,  sym_size)
    right_sprite = _load_sprite(right_name, sym_size)

    # Vertical center for symbols (slightly above center to leave label room)
    sym_y_center = height // 2 - int(height * 0.04)

    # Horizontal layout
    margin  = int(width * 0.15)
    gap     = int(width * 0.04)

    left_w  = left_sprite.width  if left_sprite  else sym_size
    right_w = right_sprite.width if right_sprite else sym_size

    left_x   = margin
    right_x  = width - margin - right_w
    arrow_x1 = left_x + left_w + gap
    arrow_x2 = right_x - gap
    arrow_y  = sym_y_center

    # Vertical position of symbols centered on arrow_y
    left_y  = arrow_y - (left_sprite.height  if left_sprite  else sym_size) // 2
    right_y = arrow_y - (right_sprite.height if right_sprite else sym_size) // 2

    draw = ImageDraw.Draw(img)

    if left_sprite:
        img.paste(left_sprite,  (left_x,  left_y),  left_sprite)
    if right_sprite:
        img.paste(right_sprite, (right_x, right_y), right_sprite)

    thickness = max(8, height // 90)
    _draw_arrow(draw, arrow_x1, arrow_x2, arrow_y, arrow_color, thickness)

    # Labels below symbols
    if labels:
        font      = _load_font(max(32, height // 24))
        label_y   = arrow_y + sym_size // 2 + int(height * 0.025)
        fg_color  = pal.get("frame_fg", (20, 20, 20))
        centers   = [
            left_x  + left_w  // 2,
            right_x + right_w // 2,
        ]
        for i, label in enumerate(labels[:2]):
            if i < len(centers):
                bb = draw.textbbox((0, 0), label, font=font)
                lw = bb[2] - bb[0]
                draw.text((centers[i] - lw // 2, label_y), label, font=font, fill=fg_color)

    img.save(output_path)
