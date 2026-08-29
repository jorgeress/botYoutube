"""
Generate 4 YouTube thumbnail variants at 1280×720 via pure PIL, no ComfyUI needed.

Variant recipes:
  thumb_1_hook.png: Vibrant solid color + bold title + sprite accent
  thumb_2_dark.png: Dark background + yellow title + large sprite
  thumb_3_split.png: Problem (red left) / Solution (green right) split
  thumb_4_minimal.png: White background + giant concept word

Output: output/<slug>/thumbnails/*.png

Usage:
    python scripts/generate_thumbnails.py [slug]
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)


# ── Dimensions ────────────────────────────────────────────────────────────────

W, H = 1280, 720

SAFE_PAD = 60        # inset from edge for all text/sprites
SPRITE_HERO = 240    # size of the big sprite in variants 1+2
SPRITE_ACCENT = 140  # size of small sprite in variant 4


# ── Color themes ──────────────────────────────────────────────────────────────

_THEMES: list[tuple[list[str], str, str, str]] = [
    # keywords, primary, accent, dark
    (["procrastinat", "avoid", "delay"],    "#E85D04", "#FFBA08", "#0D0D0D"),
    (["habit", "routine", "loop"],          "#0077B6", "#90E0EF", "#03045E"),
    (["brain", "dopamine", "neural"],       "#7209B7", "#F72585", "#0D0D0D"),
    (["sleep", "rest", "tired"],            "#023E8A", "#48CAE4", "#03045E"),
    (["stress", "anxiety", "fear"],         "#C1121F", "#FFB703", "#0D0D0D"),
    (["memory", "learn", "recall"],         "#2D6A4F", "#95D5B2", "#081C15"),
    (["focus", "attention", "distract"],    "#1B4332", "#52B788", "#081C15"),
    (["motivat", "goal", "success"],        "#F77F00", "#FCBF49", "#0D0D0D"),
]
_DEFAULT_THEME = ("#2B4590", "#FFD700", "#0D0D0D")


def _pick_theme(text: str) -> tuple[str, str, str]:
    t = text.lower()
    for keywords, primary, accent, dark in _THEMES:
        if any(k in t for k in keywords):
            return primary, accent, dark
    return _DEFAULT_THEME


def _hex(h: str) -> tuple:
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _darken(color: str, f: float = 0.55) -> tuple:
    r, g, b = _hex(color)
    return (int(r * f), int(g * f), int(b * f))


# ── Font loader ────────────────────────────────────────────────────────────────

def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = (
        ["C:/Windows/Fonts/ariblk.ttf",
         "C:/Windows/Fonts/arialbd.ttf",
         "C:/Windows/Fonts/calibrib.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ── Text helpers ──────────────────────────────────────────────────────────────

def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Word-wrap text to fit within max_w pixels."""
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words, lines, cur = text.split(), [], []
    for word in words:
        test = " ".join(cur + [word])
        bb = dummy.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_w:
            cur.append(word)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [word]
    if cur:
        lines.append(" ".join(cur))
    return lines or [text]


def _fit_text(text: str, max_w: int, max_h: int, start_size: int = 120,
              bold: bool = True) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Return (font, lines) with the largest size fitting inside max_w × max_h.
    Checks both width and height, handles long single words that can't be wrapped."""
    size = start_size
    dummy_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    while size >= 22:
        f = _font(size, bold)
        lines = _wrap(text, f, max_w)
        total_h = sum(dummy_draw.textbbox((0, 0), l, font=f)[3] + 10 for l in lines)
        max_line_w = max(dummy_draw.textbbox((0, 0), l, font=f)[2] for l in lines)
        if total_h <= max_h and max_line_w <= max_w:
            return f, lines
        size = int(size * 0.82)
    return _font(22, bold), _wrap(text, _font(22, bold), max_w)


def _outlined(draw: ImageDraw.ImageDraw, text: str, x: int, y: int,
               font: ImageFont.FreeTypeFont,
               fill: tuple, outline: tuple, stroke: int = 4) -> None:
    """Draw text with a filled stroke outline for legibility on any background."""
    for dx in range(-stroke, stroke + 1):
        for dy in range(-stroke, stroke + 1):
            if (dx != 0 or dy != 0) and abs(dx) + abs(dy) <= stroke + 1:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _block(draw: ImageDraw.ImageDraw, lines: list[str],
            font: ImageFont.FreeTypeFont, cx: int, y: int,
            fill: tuple, outline: tuple, spacing: int = 8, stroke: int = 4) -> int:
    """Draw centered text block; returns final y after last line."""
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for line in lines:
        bb = dummy.textbbox((0, 0), line, font=font)
        lw = bb[2] - bb[0]
        lh = bb[3] - bb[1]
        _outlined(draw, line, cx - lw // 2, y, font, fill, outline, stroke)
        y += lh + spacing
    return y


# ── Sprite loader ─────────────────────────────────────────────────────────────

def _sprite(name: str, target_w: int, tint: tuple | None = None) -> Image.Image | None:
    """Load sprite PNG, resize to target_w, optionally tint to a color."""
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "assets", "sprites")
    for suffix in ("_a.png", "_b.png"):
        path = os.path.join(assets_dir, f"{name}{suffix}")
        if os.path.exists(path):
            try:
                img = Image.open(path).convert("RGBA")
                aspect = img.height / img.width
                new_h = max(1, int(target_w * aspect))
                img = img.resize((target_w, new_h), Image.LANCZOS)
                if tint:
                    r, g, b = tint
                    pixels = img.load()
                    for py in range(img.height):
                        for px in range(img.width):
                            pr, pg, pb, pa = pixels[px, py]
                            if pa > 10:  # only tint non-transparent pixels
                                pixels[px, py] = (r, g, b, pa)
                return img
            except Exception:
                pass
    return None


def _paste_sprite(canvas: Image.Image, sp: Image.Image | None,
                   x: int, y: int, opacity: float = 1.0) -> None:
    if sp is None:
        return
    if opacity < 1.0:
        r, g, b, a = sp.split()
        a = a.point(lambda v: int(v * opacity))
        sp = Image.merge("RGBA", (r, g, b, a))
    x = max(0, min(x, canvas.width - sp.width))
    y = max(0, min(y, canvas.height - sp.height))
    canvas.paste(sp, (x, y), sp)


# ── Data extraction ────────────────────────────────────────────────────────────

_CONCEPT_SPRITE = [
    (["procrastinat", "avoid", "delay", "loop", "cycle"], "circular-arrow"),
    (["brain", "dopamine", "neuron", "neural", "mind"],   "brain-small"),
    (["sleep", "rest", "tired", "fatigue"],               "zzz"),
    (["idea", "insight", "discover", "research"],         "lightbulb"),
    (["time", "minute", "hour", "clock", "deadline"],     "clock-small"),
    (["goal", "success", "win", "achieve"],               "star"),
    (["heart", "love", "health"],                         "heart"),
    (["alert", "alarm", "threat", "danger"],              "exclamation"),
]


def _auto_sprite(title: str, concept: str, narration: str) -> str:
    text = (title + " " + concept + " " + narration).lower()
    for keywords, sprite_name in _CONCEPT_SPRITE:
        if any(k in text for k in keywords):
            return sprite_name
    return "lightbulb"


_SPLIT_WORDS: list[tuple[list[str], str, str]] = [
    (["procrastinat", "delay", "avoid"],  "STUCK",      "MOVING"),
    (["anxiety", "stress", "worry"],       "ANXIOUS",    "CALM"),
    (["habit", "routine"],                 "BEFORE",     "AFTER"),
    (["memory", "learn", "recall"],        "FORGET",     "REMEMBER"),
    (["focus", "distract"],                "SCATTERED",  "FOCUSED"),
    (["motivat"],                          "STUCK",      "DRIVEN"),
    (["sleep", "tired", "rest"],           "TIRED",      "RESTED"),
    (["dopamine", "brain"],                "REACTIVE",   "IN CONTROL"),
]


def _split_words(title: str) -> tuple[str, str]:
    t = title.lower()
    for keywords, bad, good in _SPLIT_WORDS:
        if any(k in t for k in keywords):
            return bad, good
    return "BEFORE", "AFTER"


def _short_title(title: str) -> str:
    """Condense title to a 3-5 word punchy form for thumbnail."""
    t = re.sub(r'\(.*?\)', '', title).strip()
    t = re.sub(r'^Why You\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^How to\s+', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^The\s+', '', t, flags=re.IGNORECASE)
    words = t.split()[:5]
    return " ".join(words).upper()


# ── Thumbnail variants ────────────────────────────────────────────────────────

def _variant_1_hook(title: str, concept: str, sprite_name: str,
                     primary: str, accent: str) -> Image.Image:
    """Vibrant solid color background + bold title + sprite accent bottom-right."""
    canvas = Image.new("RGB", (W, H), _hex(primary))
    draw = ImageDraw.Draw(canvas)

    # Diagonal gradient-ish shadow at bottom 40%
    shadow_rgb = _darken(primary, 0.55)
    for y in range(H * 3 // 5, H):
        frac = (y - H * 3 // 5) / (H * 2 // 5)
        r = int(_hex(primary)[0] * (1 - frac * 0.45) + shadow_rgb[0] * frac * 0.45)
        g = int(_hex(primary)[1] * (1 - frac * 0.45) + shadow_rgb[1] * frac * 0.45)
        b = int(_hex(primary)[2] * (1 - frac * 0.45) + shadow_rgb[2] * frac * 0.45)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Sprite bottom-right at 40% opacity (background layer)
    sp = _sprite(sprite_name, SPRITE_HERO + 60)
    if sp:
        _paste_sprite(canvas, sp, W - sp.width - 20, H - sp.height - 10, opacity=0.25)

    # Title text (max left 75% to avoid sprite overlap)
    text_max_w = W - SAFE_PAD * 2 - 80
    text_max_h = H - SAFE_PAD * 2 - 80
    short = _short_title(title)
    f, lines = _fit_text(short, text_max_w, text_max_h, start_size=130)

    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    total_h = sum(dummy.textbbox((0, 0), l, font=f)[3] + 10 for l in lines)
    y_start = (H - total_h) // 2 - 20
    _block(draw, lines, f, W // 2, y_start, (255, 255, 255), _darken(primary, 0.2), 10, 5)

    # Concept accent label bottom-left
    f_sub = _font(50)
    _outlined(draw, concept, SAFE_PAD, H - 80, f_sub, _hex(accent), (0, 0, 0), 3)

    # Sprite on top (smaller, full opacity)
    sp2 = _sprite(sprite_name, SPRITE_HERO)
    if sp2:
        _paste_sprite(canvas, sp2, W - sp2.width - SAFE_PAD, H - sp2.height - SAFE_PAD)

    return canvas


def _variant_2_dark(title: str, concept: str, sprite_name: str,
                     accent: str, dark: str) -> Image.Image:
    """Dark background + bright accent text + large sprite right."""
    canvas = Image.new("RGB", (W, H), _hex(dark))
    draw = ImageDraw.Draw(canvas)

    # Subtle vignette (darker edges)
    for r_val in range(0, 80, 4):
        alpha = (80 - r_val) / 80 * 60
        dark_col = tuple(min(255, int(c + alpha * 0.05)) for c in _hex(dark))
        draw.rectangle([(r_val, r_val), (W - r_val, H - r_val)],
                        outline=tuple(max(0, c - 8) for c in _hex(dark)))

    # Large sprite right side (at 30% opacity as watermark)
    sp_big = _sprite(sprite_name, SPRITE_HERO + 120, tint=(200, 200, 200))
    if sp_big:
        _paste_sprite(canvas, sp_big,
                       W - sp_big.width - 30, (H - sp_big.height) // 2, opacity=0.18)

    # Concept word in accent color (large, left-aligned)
    f_concept = _font(90)
    _outlined(draw, concept, SAFE_PAD, SAFE_PAD + 10,
               f_concept, _hex(accent), (0, 0, 0), 4)

    # Divider line under concept
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bb = dummy.textbbox((0, 0), concept, font=f_concept)
    line_y = SAFE_PAD + 10 + bb[3] + 12
    draw.rectangle([SAFE_PAD, line_y, SAFE_PAD + bb[2] - bb[0], line_y + 5],
                    fill=_hex(accent))

    # Title below divider (white, smaller)
    short = _short_title(title)
    f_title, lines = _fit_text(short, W - SAFE_PAD * 2 - 200, H - line_y - SAFE_PAD - 60,
                                 start_size=75)
    _block(draw, lines, f_title, W // 2 - 50, line_y + 20,
            (240, 240, 240), (10, 10, 10), 8, 4)

    # Sprite bottom-right (full opacity, smaller)
    sp = _sprite(sprite_name, SPRITE_HERO, tint=_hex(accent))
    if sp:
        _paste_sprite(canvas, sp, W - sp.width - SAFE_PAD, H - sp.height - SAFE_PAD)

    return canvas


def _variant_3_split(title: str, sprite_name: str, primary: str) -> Image.Image:
    """Problem (red/dark left) vs Solution (green right) split."""
    LEFT_COLOR  = "#8B0000"   # deep red
    RIGHT_COLOR = "#005C00"   # deep green
    LEFT_ACCENT  = "#FF6B6B"
    RIGHT_ACCENT = "#6BCB77"

    canvas = Image.new("RGB", (W, H), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    mid = W // 2

    # Fill halves
    draw.rectangle([0, 0, mid, H], fill=_hex(LEFT_COLOR))
    draw.rectangle([mid, 0, W, H], fill=_hex(RIGHT_COLOR))

    # Thin divider bar with arrow
    draw.rectangle([mid - 4, 0, mid + 4, H], fill=(20, 20, 20))
    # Arrow pointing right at center
    cx, cy = mid, H // 2
    arrow_pts = [(cx - 20, cy - 28), (cx + 20, cy), (cx - 20, cy + 28)]
    draw.polygon(arrow_pts, fill=(255, 255, 255))

    bad_word, good_word = _split_words(title)

    # Left side: problem word
    f_bad, bad_lines = _fit_text(bad_word, mid - SAFE_PAD * 2, H // 2 - 40, start_size=110)
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    total_h = sum(dummy.textbbox((0, 0), l, font=f_bad)[3] + 8 for l in bad_lines)
    _block(draw, bad_lines, f_bad, mid // 2, (H - total_h) // 2 - 20,
            _hex(LEFT_ACCENT), _hex(LEFT_COLOR), 8, 4)

    # Left sprite (red-x): white tint so it shows on red background
    sp_bad = _sprite("red-x", 150, tint=(255, 180, 180)) or _sprite("exclamation", 150, tint=(255, 200, 200))
    if sp_bad:
        _paste_sprite(canvas, sp_bad, mid // 2 - sp_bad.width // 2,
                       H - sp_bad.height - SAFE_PAD, opacity=0.75)

    # Right side: solution word
    f_good, good_lines = _fit_text(good_word, mid - SAFE_PAD * 2, H // 2 - 40, start_size=110)
    total_h = sum(dummy.textbbox((0, 0), l, font=f_good)[3] + 8 for l in good_lines)
    _block(draw, good_lines, f_good, mid + mid // 2, (H - total_h) // 2 - 20,
            _hex(RIGHT_ACCENT), _hex(RIGHT_COLOR), 8, 4)

    # Right sprite (check): white tint so it shows on green background
    sp_good = _sprite("check", 150, tint=(180, 255, 180)) or _sprite("lightbulb", 150, tint=(200, 255, 200))
    if sp_good:
        _paste_sprite(canvas, sp_good, mid + mid // 2 - sp_good.width // 2,
                       H - sp_good.height - SAFE_PAD, opacity=0.75)

    # Title bar at top (full width, slightly transparent dark overlay)
    bar_h = 80
    bar_img = Image.new("RGBA", (W, bar_h), (0, 0, 0, 180))
    canvas.paste(Image.new("RGB", (W, bar_h), (0, 0, 0)), (0, 0), bar_img)
    draw2 = ImageDraw.Draw(canvas)
    short = title.upper()[:50]  # keep as-is but uppercase, cut off long
    f_top = _font(42)
    bb = dummy.textbbox((0, 0), short, font=f_top)
    while bb[2] - bb[0] > W - SAFE_PAD * 2:
        words = short.rsplit(" ", 1)
        if len(words) < 2:
            break
        short = words[0] + "..."
        bb = dummy.textbbox((0, 0), short, font=f_top)
    tw = bb[2] - bb[0]
    _outlined(draw2, short, (W - tw) // 2, (bar_h - (bb[3] - bb[1])) // 2,
               f_top, (255, 255, 255), (0, 0, 0), 3)

    return canvas


def _variant_4_minimal(title: str, concept: str, sprite_name: str, primary: str) -> Image.Image:
    """White background + giant concept word + colored accent bar."""
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Left accent bar
    bar_w = 18
    draw.rectangle([0, 0, bar_w, H], fill=_hex(primary))

    # Large sprite bottom-right (light tint)
    sp_bg = _sprite(sprite_name, SPRITE_HERO + 80, tint=_hex(primary))
    if sp_bg:
        _paste_sprite(canvas, sp_bg, W - sp_bg.width - SAFE_PAD,
                       H - sp_bg.height - 20, opacity=0.12)

    # Concept word: huge, but must stay within safe margins on both sides
    concept_text = concept.upper()
    safe_text_w = W - bar_w - SAFE_PAD * 2 - 40   # room between bar and right edge
    f_hero, hero_lines = _fit_text(concept_text, safe_text_w,
                                    H // 2 - 30, start_size=150)
    dummy = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    total_h = sum(dummy.textbbox((0, 0), l, font=f_hero)[3] + 6 for l in hero_lines)
    y_hero = SAFE_PAD + 30
    cx = bar_w + SAFE_PAD + safe_text_w // 2   # center of the text zone (not full canvas)
    _block(draw, hero_lines, f_hero, cx, y_hero, (20, 20, 20), (255, 255, 255), 6, 2)

    # Accent underline below concept
    ul_y = y_hero + total_h + 16
    ul_w = min(safe_text_w - 40, 700)
    draw.rectangle([cx - ul_w // 2, ul_y, cx + ul_w // 2, ul_y + 8],
                    fill=_hex(primary))

    # Subtitle / hook phrase
    short = _short_title(title)
    if short.upper() == concept.upper():
        short = "THE TRUTH BEHIND IT"
    f_sub, sub_lines = _fit_text(short, safe_text_w - 60,
                                   H - ul_y - SAFE_PAD * 2 - 40, start_size=70)
    _block(draw, sub_lines, f_sub, cx, ul_y + 28, (60, 60, 60), (255, 255, 255), 6, 2)

    # Small sprite bottom-right (full opacity)
    sp = _sprite(sprite_name, SPRITE_ACCENT)
    if sp:
        _paste_sprite(canvas, sp, W - sp.width - SAFE_PAD, H - sp.height - SAFE_PAD)

    return canvas


# ── Main ──────────────────────────────────────────────────────────────────────

def generate_thumbnails(slug: str) -> None:
    out_dir   = os.path.join(OUTPUT_DIR, slug)
    seg_path  = os.path.join(out_dir, "segments.json")
    thumb_dir = os.path.join(out_dir, "thumbnails")

    if not os.path.exists(seg_path):
        print(f"ERROR: {seg_path} not found. Run parse_script.py first.")
        sys.exit(1)

    with open(seg_path, encoding="utf-8") as f:
        data = json.load(f)

    title  = data.get("title", slug)
    beats  = data.get("beats", [])

    # Extract concept from first text-frame beat
    concept = ""
    for beat in beats:
        fields = beat.get("fields") or {}
        if fields.get("shot") == "text-frame":
            concept = fields.get("text", "").strip("'\"")
            break
    if not concept:
        concept = _short_title(title)

    hook_narr = beats[0].get("narration", "") if beats else ""
    sprite    = _auto_sprite(title, concept, hook_narr)

    primary, accent, dark = _pick_theme(title + " " + hook_narr)

    print(f"Generating thumbnails for: {title}")
    print(f"  concept={concept!r}  sprite={sprite}  theme={primary}/{accent}")

    os.makedirs(thumb_dir, exist_ok=True)

    variants = [
        ("thumb_1_hook.png",    lambda: _variant_1_hook(title, concept, sprite, primary, accent)),
        ("thumb_2_dark.png",    lambda: _variant_2_dark(title, concept, sprite, accent, dark)),
        ("thumb_3_split.png",   lambda: _variant_3_split(title, sprite, primary)),
        ("thumb_4_minimal.png", lambda: _variant_4_minimal(title, concept, sprite, primary)),
    ]

    for filename, fn in variants:
        path = os.path.join(thumb_dir, filename)
        img = fn()
        img.save(path)
        print(f"  Saved: {path}")

    print(f"\n4 thumbnails in: {thumb_dir}")
    print("Open them side by side and pick the best one.")


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def main():
    slug_arg = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    slug = find_slug(slug_arg)
    generate_thumbnails(slug)


if __name__ == "__main__":
    main()
