"""
PIL sprite compositing for structured beat overlays.

Sprites are PNG RGBA files in assets/sprites/, generated with Flux + rembg.
Each sprite has two variants: <name>_a.png and <name>_b.png.
The variant is chosen deterministically from the beat seed so renders are
reproducible but not clonal between beats.

Sprite generation: run tools/generate_sprites.py (requires ComfyUI + rembg).
If a sprite file does not exist, compositing is silently skipped for that sprite.

Integration: called from _comfyui.py after the Flux _src.png is saved,
before create_clip(). Also called for PIL-rendered beats (text_frame, diagram)
after the PIL render saves the image.
"""

from __future__ import annotations
import os
from PIL import Image

# Anchor positions as (x_frac, y_frac), top-left corner of sprite (after centering)
ANCHORS: dict[str, tuple[float, float]] = {
    "top-left":      (0.08, 0.08),
    "top-right":     (0.82, 0.08),
    "top-center":    (0.45, 0.06),
    "above-char":    (0.45, 0.12),
    "left-mid":      (0.08, 0.40),
    "right-mid":     (0.80, 0.40),
    "bottom-corner": (0.84, 0.78),
}

_SPRITES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "sprites",
)


def _sprite_path(name: str, variant: int) -> str:
    suffix = "a" if variant % 2 == 0 else "b"
    path = os.path.join(_SPRITES_DIR, f"{name}_{suffix}.png")
    if not os.path.exists(path):
        path = os.path.join(_SPRITES_DIR, f"{name}.png")
    return path


def composite_sprite(base_img: Image.Image, sprite_name: str, anchor: str,
                     scale: float, seed: int) -> Image.Image:
    """
    Composite one sprite PNG onto base_img and return the modified image.
    No-op (returns original) if the sprite file does not exist.
    """
    path = _sprite_path(sprite_name, seed)
    if not os.path.exists(path):
        return base_img

    W, H = base_img.size
    sprite = Image.open(path).convert("RGBA")

    # Size: scale * W with tight ±5% jitter seeded deterministically
    jitter = 1.0 + ((seed % 11) / 100.0 - 0.05)
    target_w = max(1, int(W * scale * jitter))
    ratio = target_w / sprite.width
    target_h = max(1, int(sprite.height * ratio))
    sprite = sprite.resize((target_w, target_h), Image.LANCZOS)

    # Rotation: ±3 degrees seeded deterministically
    angle = float((seed % 7) - 3)
    if angle != 0.0:
        sprite = sprite.rotate(angle, expand=True, resample=Image.BICUBIC)

    # Position: anchor as fraction of frame, centered on anchor point
    ax, ay = ANCHORS.get(anchor, (0.45, 0.06))
    x = int(W * ax) - sprite.width // 2
    y = int(H * ay) - sprite.height // 2
    x = max(0, min(x, W - sprite.width))
    y = max(0, min(y, H - sprite.height))

    out = base_img.copy().convert("RGBA")
    out.paste(sprite, (x, y), sprite)
    return out.convert("RGB")


def composite_sprites(img_path: str, sprites_meta: list[dict],
                      seed: int, width: int, height: int) -> None:
    """
    Apply all sprites in sprites_meta to the image file at img_path.
    Overwrites the file in place. No-op if sprites_meta is empty.
    """
    if not sprites_meta:
        return
    base = Image.open(img_path).convert("RGB")
    for sm in sprites_meta:
        name   = sm.get("name", "")
        anchor = sm.get("anchor", "top-right")
        scale  = float(sm.get("scale", 0.10))
        if name:
            base = composite_sprite(base, name, anchor, scale, seed)
    base.save(img_path)


def composite_place_label(img_path: str, place_text: str,
                          font_paths: list[str]) -> None:
    """
    Write place_text in Caveat-Bold onto the building sign area of img_path.
    Fixed box position: x 8-30% of width, y 12-22% of height.
    The building-sign Flux fragment positions the sign in the upper-left quadrant.
    """
    from PIL import ImageDraw, ImageFont

    img = Image.open(img_path).convert("RGB")
    W, H = img.size

    # Sign bounding box: fixed position matching the Flux building prompt
    box_x1 = int(W * 0.08)
    box_x2 = int(W * 0.30)
    box_y1 = int(H * 0.12)
    box_y2 = int(H * 0.22)
    box_w  = box_x2 - box_x1
    box_h  = box_y2 - box_y1

    draw = ImageDraw.Draw(img)
    text = place_text.upper()

    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                # Auto-size to fit box
                for size in range(box_h, 10, -2):
                    f = ImageFont.truetype(fp, size)
                    bb = draw.textbbox((0, 0), text, font=f)
                    if (bb[2] - bb[0]) <= box_w * 0.9 and (bb[3] - bb[1]) <= box_h * 0.9:
                        font = f
                        break
                if font:
                    break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    tx = box_x1 + (box_w - tw) // 2
    ty = box_y1 + (box_h - th) // 2 - bb[1]

    # White background fill on sign area, then dark text
    draw.rectangle([box_x1, box_y1, box_x2, box_y2], fill=(255, 255, 255))
    draw.text((tx + 2, ty + 2), text, font=font, fill=(200, 200, 200))  # shadow
    draw.text((tx, ty),         text, font=font, fill=(20, 20, 20))

    img.save(img_path)
