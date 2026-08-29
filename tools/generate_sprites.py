"""
Sprite generation helper: creates assets/sprites/ PNG RGBA files.

Two generation paths:
  PIL_SPRITES: drawn directly in PIL (Caveat font + geometric shapes).
                 Used for sprites Flux consistently gets wrong: text/letters,
                 clocks with hands, anything requiring exact geometry.
  SPRITE_CATALOG: generated via ComfyUI Flux (organic shapes: sun, brain, etc.)
                 Background removed with luminance threshold from _raw.png.

Usage:
    python tools/generate_sprites.py              # generate all missing sprites
    python tools/generate_sprites.py --sprite zzz # generate/regenerate one sprite
    python tools/generate_sprites.py --reprocess  # re-apply threshold to all _raw.png

Run once. Sprites are committed to the repo and reused across all videos.
"""

import json
import os
import sys
import time
import urllib.request
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import COMFYUI_URL, COMFYUI_CLIP1, COMFYUI_CLIP2, COMFYUI_VAE, COMFYUI_UNET

SPRITES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "assets", "sprites")

# Sprites drawn in PIL: Flux is unreliable for text/letters/exact geometry.
# Generated instantly with no GPU. Two identical variants saved (_a, _b).
PIL_SPRITES = {
    "zzz", "clock-small",
    "arrow-up", "arrow-down", "arrow-left",
    "star", "heart",
    *[f"number-{d}" for d in range(10)],
}

# Flux-generated sprites (organic shapes Flux handles well)
# Each entry: (name, flux_desc, n_seeds)
SPRITE_CATALOG = [
    ("sun",             "yellow sun with rays",                        4),
    ("circular-arrow",  "circular loop arrow",                         4),
    ("question-mark",   "bold question mark",                          4),
    ("lightbulb",       "glowing yellow lightbulb",                    4),
    ("check",           "green check mark",                            4),
    ("red-x",           "bold red X mark",                             4),
    ("arrow-right",     "bold arrow pointing right",                   4),
    ("exclamation",     "bold exclamation mark",                       4),
    ("brain-small",     "simple brain outline",                        4),
    ("thought-bubble",  "empty thought bubble",                        4),
]

# ── PIL sprite drawing functions ─────────────────────────────────────────────

def _font_paths() -> list[str]:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from config import FONT_PATHS_BOLD
        return FONT_PATHS_BOLD
    except Exception:
        return []


def _draw_zzz(size: int = 512) -> "Image.Image":
    """Three Z characters in ascending staircase, rough-ink style."""
    from PIL import Image, ImageDraw, ImageFont
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    font = None
    for fp in _font_paths():
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, int(size * 0.28))
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    ink = (30, 30, 30, 255)
    chars = [
        ("z", 0.18, 0.52),   # small, lower-left
        ("Z", 0.38, 0.32),   # medium, center
        ("Z", 0.58, 0.12),   # large, upper-right
    ]
    sizes = [int(size * f) for f in (0.20, 0.26, 0.32)]

    for i, (ch, xf, yf) in enumerate(chars):
        fnt = None
        for fp in _font_paths():
            if os.path.exists(fp):
                try:
                    fnt = ImageFont.truetype(fp, sizes[i])
                    break
                except Exception:
                    continue
        if fnt is None:
            fnt = font
        bb = draw.textbbox((0, 0), ch.upper(), font=fnt)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        x = int(size * xf) - w // 2
        y = int(size * yf) - h // 2
        draw.text((x, y), ch.upper(), font=fnt, fill=ink)

    return img


def _draw_clock(size: int = 512) -> "Image.Image":
    """Simple analog clock face: circle + 12 tick marks + hour/minute hands."""
    import math
    from PIL import Image, ImageDraw
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r      = int(size * 0.40)
    lw     = max(4, size // 60)   # line width scales with size
    ink    = (30, 30, 30, 255)

    # Outer circle
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink, width=lw * 2)

    # 12 tick marks
    for i in range(12):
        angle  = math.radians(i * 30 - 90)
        r_out  = r - lw
        r_in   = r - lw * (4 if i % 3 == 0 else 2)
        x1     = cx + r_out * math.cos(angle)
        y1     = cy + r_out * math.sin(angle)
        x2     = cx + r_in  * math.cos(angle)
        y2     = cy + r_in  * math.sin(angle)
        draw.line([(x1, y1), (x2, y2)], fill=ink, width=lw)

    # Hour hand  (pointing roughly to 10 o'clock)
    hour_angle = math.radians(-60)
    draw.line([(cx, cy),
               (cx + r * 0.50 * math.cos(hour_angle),
                cy + r * 0.50 * math.sin(hour_angle))],
              fill=ink, width=lw * 3)

    # Minute hand (pointing roughly to 2 o'clock)
    min_angle = math.radians(60)
    draw.line([(cx, cy),
               (cx + r * 0.75 * math.cos(min_angle),
                cy + r * 0.75 * math.sin(min_angle))],
              fill=ink, width=lw * 2)

    # Center dot
    dot = lw * 2
    draw.ellipse([cx - dot, cy - dot, cx + dot, cy + dot], fill=ink)

    return img


def _draw_arrow_dir(size: int = 512, direction: str = "up") -> "Image.Image":
    """Bold directional arrow (up / down / left). Right is already a Flux sprite."""
    import math
    from PIL import Image, ImageDraw
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    ink  = (30, 30, 30, 255)
    cx, cy = size // 2, size // 2
    shaft_w = max(6, size // 24)
    head_w  = int(size * 0.28)
    head_h  = int(size * 0.32)
    shaft_l = int(size * 0.28)

    # Build arrow pointing UP, then rotate
    # Shaft: rectangle centered at cx, below center; Head: triangle above
    rotations = {"up": 0, "down": 180, "left": 270}
    angle = rotations.get(direction, 0)

    # Shaft rect (pointing up)
    sx1, sy1 = cx - shaft_w // 2, cy - shaft_l // 2
    sx2, sy2 = cx + shaft_w // 2, cy + shaft_l // 2 + head_h // 2
    draw.rectangle([sx1, sy1, sx2, sy2], fill=ink)

    # Arrowhead triangle (pointing up)
    tip_y  = cy - shaft_l // 2 - head_h // 2
    base_y = cy - shaft_l // 2 + head_h // 2
    draw.polygon([(cx, tip_y),
                  (cx - head_w // 2, base_y),
                  (cx + head_w // 2, base_y)], fill=ink)

    if angle:
        img = img.rotate(-angle, expand=False, resample=2)
    return img


def _draw_star(size: int = 512) -> "Image.Image":
    """5-pointed star, yellow fill with black outline."""
    import math
    from PIL import Image, ImageDraw
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    r_out  = int(size * 0.40)
    r_in   = int(size * 0.17)
    lw     = max(4, size // 48)
    pts = []
    for i in range(10):
        angle = math.radians(i * 36 - 90)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=(240, 200, 30, 255), outline=(30, 30, 30, 255))
    # Re-draw outline thicker
    for i in range(10):
        draw.line([pts[i], pts[(i + 1) % 10]], fill=(30, 30, 30, 255), width=lw)
    return img


def _draw_heart(size: int = 512) -> "Image.Image":
    """Red heart: two overlapping circles + downward triangle."""
    import math
    from PIL import Image, ImageDraw
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    fill = (210, 40, 40, 255)
    ink  = (30, 30, 30, 255)
    lw   = max(4, size // 56)

    cx, cy = size // 2, size // 2
    r  = int(size * 0.20)
    # Two circles for the top bumps
    c1x, c1y = cx - r, cy - int(size * 0.06)
    c2x, c2y = cx + r, cy - int(size * 0.06)
    draw.ellipse([c1x - r, c1y - r, c1x + r, c1y + r], fill=fill, outline=ink, width=lw)
    draw.ellipse([c2x - r, c2y - r, c2x + r, c2y + r], fill=fill, outline=ink, width=lw)
    # Triangle / lower body: polygon connecting left, right, bottom tip
    bot_y   = cy + int(size * 0.33)
    left_x  = cx - int(size * 0.37)
    right_x = cx + int(size * 0.37)
    top_y   = cy - int(size * 0.06)
    draw.polygon([(left_x, top_y), (right_x, top_y), (cx, bot_y)], fill=fill)
    # Clean outline on bottom triangle edges
    draw.line([(left_x, top_y), (cx, bot_y)],  fill=ink, width=lw)
    draw.line([(right_x, top_y), (cx, bot_y)], fill=ink, width=lw)
    return img


def _draw_number_badge(digit: int, size: int = 512) -> "Image.Image":
    """Bold digit in Caveat font, centered, no circle."""
    from PIL import Image, ImageDraw, ImageFont
    img  = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    ink  = (30, 30, 30, 255)
    text = str(digit)
    font = None
    for fp in _font_paths():
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, int(size * 0.80))
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
    bb = draw.textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((cx - tw // 2 - bb[0], cy - th // 2 - bb[1]), text, font=font, fill=ink)
    return img


_PIL_DRAWERS: dict = {
    "zzz":          _draw_zzz,
    "clock-small":  _draw_clock,
    "arrow-up":     lambda s=512: _draw_arrow_dir(s, "up"),
    "arrow-down":   lambda s=512: _draw_arrow_dir(s, "down"),
    "arrow-left":   lambda s=512: _draw_arrow_dir(s, "left"),
    "star":         _draw_star,
    "heart":        _draw_heart,
    **{f"number-{d}": (lambda s=512, d=d: _draw_number_badge(d, s)) for d in range(10)},
}


def generate_pil_sprite(name: str) -> None:
    """Draw a sprite with PIL and save both _a and _b variants."""
    drawer = _PIL_DRAWERS.get(name)
    if drawer is None:
        print(f"  No PIL drawer for '{name}'")
        return
    print(f"\nGenerating sprite (PIL): {name}")
    os.makedirs(SPRITES_DIR, exist_ok=True)
    for suffix in ("_a", "_b"):
        out = os.path.join(SPRITES_DIR, f"{name}{suffix}.png")
        img = drawer(512)
        img.save(out)
        kb = os.path.getsize(out) // 1024
        print(f"  saved {name}{suffix}.png ({kb} KB, PIL)")

SPRITE_PROMPT_TEMPLATE = (
    "single hand-drawn {desc} sketch, rough black ink lines, "
    "plain white background, nothing else, isolated on white, centered"
)


def _build_workflow(prompt: str, prefix: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": COMFYUI_UNET}},
        "2": {"class_type": "DualCLIPLoader",  "inputs": {
            "clip_name1": COMFYUI_CLIP1, "clip_name2": COMFYUI_CLIP2, "type": "flux",
        }},
        "3": {"class_type": "VAELoader",       "inputs": {"vae_name": COMFYUI_VAE}},
        "4": {"class_type": "CLIPTextEncode",  "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode",  "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": 1024, "height": 1024, "batch_size": 1,
        }},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["6", 0], "seed": seed, "steps": 4,
            "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "8": {"class_type": "VAEDecode",  "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",  "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def _submit(workflow: dict) -> str:
    body = json.dumps({"prompt": workflow}).encode("utf-8")
    req  = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=body,
                                   headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["prompt_id"]


def _wait(pid: str, timeout: int = 300) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            hist = json.loads(urllib.request.urlopen(
                f"{COMFYUI_URL}/history/{pid}", timeout=10).read())
            if pid not in hist:
                continue
            status = hist[pid]["status"]
            if status.get("completed"):
                outputs = hist[pid]["outputs"]
                node    = next(iter(outputs))
                img     = outputs[node]["images"][0]
                return os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "ComfyUI", "output", img["filename"],
                ).replace("/", os.sep)
        except Exception:
            pass
    return None


def remove_bg(input_path: str, output_path: str) -> bool:
    """
    Luminance-threshold background removal for black ink on white.
    Input must be an RGB/RGBA image with a white (or near-white) background.
    Output is RGBA with white areas made transparent, ink kept opaque.
    """
    from PIL import Image, ImageFilter
    import numpy as np

    THRESHOLD = 230  # pixels with luminance >= this value → transparent background

    # Always flatten to RGB on white first, avoids issues with any prior alpha
    # (rembg sets bg pixels to black 0,0,0,0; without this they'd look like ink)
    base = Image.open(input_path).convert("RGBA")
    white_bg = Image.new("RGB", base.size, (255, 255, 255))
    white_bg.paste(base.convert("RGB"), mask=base.split()[3])  # flatten using alpha

    rgb = np.array(white_bg, dtype=np.float32)

    # Luminance (ITU-R BT.601)
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]

    # Alpha mask: dark pixels = ink (opaque), bright pixels = background (transparent)
    alpha = np.where(lum < THRESHOLD, 255, 0).astype(np.uint8)

    # Light feather on edges
    alpha_img  = Image.fromarray(alpha, mode="L")
    alpha_blur = np.array(alpha_img.filter(ImageFilter.GaussianBlur(radius=1)), dtype=np.float32)
    alpha = np.clip(np.where(alpha > 0, np.maximum(alpha.astype(np.float32), alpha_blur), alpha_blur * 0.2), 0, 255).astype(np.uint8)

    # Build RGBA output: use flattened (white-bg) RGB + new alpha
    # Transparent pixels are white (255,255,255,0), clean, no black pre-multiply
    out = np.zeros((base.height, base.width, 4), dtype=np.uint8)
    out[:, :, :3] = rgb.astype(np.uint8)
    out[:, :, 3]  = alpha
    Image.fromarray(out, mode="RGBA").save(output_path)
    return True


def generate_sprite(name: str, desc: str, n_seeds: int = 4) -> None:
    print(f"\nGenerating sprite: {name}")
    prompt = SPRITE_PROMPT_TEMPLATE.format(desc=desc)
    seeds  = [random.randint(0, 2**31) for _ in range(n_seeds)]
    imgs: list[str] = []

    for i, seed in enumerate(seeds):
        prefix = f"sprite_{name}_{i}"
        pid    = _submit(_build_workflow(prompt, prefix, seed))
        print(f"  seed {seed} -> {pid[:8]}...", end=" ", flush=True)
        path   = _wait(pid)
        if path and os.path.exists(path):
            print("OK")
            imgs.append(path)
        else:
            print("FAILED")

    if len(imgs) < 2:
        print(f"  Only {len(imgs)} images generated, skipping sprite")
        return

    os.makedirs(SPRITES_DIR, exist_ok=True)
    for variant_idx, (src, suffix) in enumerate(zip(imgs[:2], ("_a", "_b"))):
        dst_raw  = os.path.join(SPRITES_DIR, f"{name}{suffix}_raw.png")
        dst_rgba = os.path.join(SPRITES_DIR, f"{name}{suffix}.png")
        import shutil
        shutil.copy2(src, dst_raw)  # keep raw, needed for --reprocess
        ok = remove_bg(dst_raw, dst_rgba)
        if ok:
            print(f"  saved {name}{suffix}.png (RGBA, bg removed)")
        else:
            shutil.copy2(dst_raw, dst_rgba)
            print(f"  saved {name}{suffix}.png (RGB, no bg removal)")


def reprocess_existing() -> None:
    """
    Re-apply luminance threshold using the _raw.png originals (Flux output, untouched).
    Always reads from <name>_raw.png so the input is always clean white-background RGB.
    """
    import glob
    raws = sorted(glob.glob(os.path.join(SPRITES_DIR, "*_raw.png")))
    if not raws:
        print("No *_raw.png files found. Raw files are preserved from generation.")
        print("If missing, regenerate the sprites: python tools/generate_sprites.py --sprite <name>")
        return
    print(f"Reprocessing {len(raws)} sprites from _raw.png originals...")
    for raw_path in raws:
        # <name>_a_raw.png → <name>_a.png
        out_path = raw_path.replace("_raw.png", ".png")
        ok = remove_bg(raw_path, out_path)
        name = os.path.basename(out_path)
        if ok:
            print(f"  {name}: OK")
        else:
            print(f"  {name}: FAILED")


def main():
    args       = sys.argv[1:]
    reprocess  = "--reprocess" in args
    target     = next((a for a in args if not a.startswith("--")), None)

    if reprocess:
        reprocess_existing()
        return

    try:
        urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5)
    except Exception:
        print(f"ERROR: ComfyUI not running at {COMFYUI_URL}")
        print("Start ComfyUI first, then run this script.")
        sys.exit(1)

    all_names = list(PIL_SPRITES) + [n for n, _, _ in SPRITE_CATALOG]

    if target and target not in all_names:
        print(f"No sprite matching '{target}'. Available: {', '.join(all_names)}")
        sys.exit(1)

    names_to_run = [target] if target else all_names

    # PIL sprites: no ComfyUI needed
    pil_targets = [n for n in names_to_run if n in PIL_SPRITES]
    flux_targets = [n for n in names_to_run if n not in PIL_SPRITES]

    for name in pil_targets:
        out_a = os.path.join(SPRITES_DIR, f"{name}_a.png")
        if os.path.exists(out_a) and not target:
            print(f"  {name}: already exists, skipping")
            continue
        generate_pil_sprite(name)

    if not flux_targets:
        print("\nDone.")
        return

    # Flux sprites: ComfyUI required
    try:
        urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5)
    except Exception:
        print(f"ERROR: ComfyUI not running at {COMFYUI_URL}")
        print("Start ComfyUI first, then run this script.")
        sys.exit(1)

    flux_catalog = [(n, d, s) for n, d, s in SPRITE_CATALOG if n in flux_targets]
    print(f"\nGenerating {len(flux_catalog)} Flux sprites into {SPRITES_DIR}/")
    for name, desc, n_seeds in flux_catalog:
        out_a = os.path.join(SPRITES_DIR, f"{name}_a.png")
        if os.path.exists(out_a) and not target:
            print(f"  {name}: already exists, skipping (delete to regenerate)")
            continue
        generate_sprite(name, desc, n_seeds)

    print("\nDone. Run the pipeline to test sprite compositing.")


if __name__ == "__main__":
    main()
