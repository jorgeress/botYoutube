"""
PIL-based renderer for text_frame beats, skips ComfyUI entirely.

A text_frame beat is a pure text reveal: white background, large bold centered
text, clean shadow. No icons, no overlays. ComfyUI is never called for them.

Used by:
  _comfyui.py          -- generates the _src.png before create_clip()
  parse_script.py      -- classify_beat_type() uses is_text_frame()
  generate_image_prompts.py -- skips Flux prompt building for text_frame beats
"""

from __future__ import annotations
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont
from config import STYLE_PALETTE, FONT_PATHS_BOLD

_FONT_BOLD = FONT_PATHS_BOLD

_TEXT_FRAME_RE = re.compile(
    r"large\s+bold|large\s+hand-drawn\s+text|bold\s+text\s+'|"
    r"standalone\s+text|centered\s+text|large\s+text\s+'|"
    r"text\s+frame|text\s+reveal",
    re.IGNORECASE,
)

# If a character is explicitly described alongside the text, it's a scene beat --
# Flux handles the character + in-scene text composition, not a pure text reveal.
_CHAR_KW_TF = [
    "stickman", "stick figure", "figure pointing", "person pointing",
    "character pointing", "scientist", "teacher", "researcher",
]

def is_text_frame(visual: str) -> bool:
    """
    True only when the visual is a PURE text reveal (no character described).
    If a character is explicitly mentioned alongside text, it's a scene beat --
    the writer wants a stickman + in-scene text, not a plain text card.
    """
    if not _TEXT_FRAME_RE.search(visual):
        return False
    v = visual.lower()
    if any(k in v for k in _CHAR_KW_TF):
        return False
    return True


def extract_frame_text(visual: str) -> str:
    """Extract the text to display from the visual description."""
    m = re.search(r"'([^']+)'", visual)
    if m:
        return m.group(1).upper()
    cleaned = re.sub(
        r"large\s+bold|hand-drawn|centered\s+on\s+screen|"
        r"red\s+dashed\s+underline|simple\s+decorative\s+underline|"
        r"standalone\s+text|text\s+frame|text\s+reveal|"
        r"white\s+background|below\s+it",
        "", visual, flags=re.IGNORECASE,
    )
    return cleaned.strip(" ,.'").upper()[:40]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_BOLD:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _measure(draw: ImageDraw.Draw, text: str, font) -> tuple[int, int]:
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]


def render_text_frame(visual: str, output_path: str,
                      width: int = 1920, height: int = 1080,
                      icon_top: bool = False) -> None:
    """
    Render a clean text frame: white background, large bold centered text, drop shadow.
    icon_top=True shifts the text to the lower 60% of the frame so a sprite
    composited above it (via _sprites.composite_sprites) has clear visual space.
    """
    pal  = STYLE_PALETTE
    text = extract_frame_text(visual)

    img  = Image.new("RGB", (width, height), pal["frame_bg"])
    draw = ImageDraw.Draw(img)

    # Auto-size: largest font that fits within 78% of frame width
    font = _load_font(40)
    for font_size in range(180, 38, -6):
        font = _load_font(font_size)
        tw, _ = _measure(draw, text, font)
        if tw <= width * 0.78:
            break

    # Full bbox accounts for font glyph offset (bb[1] shifts visual top)
    bb = draw.textbbox((0, 0), text, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]

    # When an icon sits at the top (~top 30% of frame), center text in the lower area.
    # icon_top=False: standard vertical center; icon_top=True: 62% down.
    center_y = int(height * 0.62) if icon_top else height // 2
    y = center_y - th // 2 - bb[1]
    x = (width - tw) // 2

    draw.text((x + 4, y + 4), text, font=font, fill=pal["frame_shadow"])
    draw.text((x, y),         text, font=font, fill=pal["frame_fg"])

    img.save(output_path)
