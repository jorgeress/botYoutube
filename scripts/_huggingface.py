"""
Hugging Face Inference API image generation + FFmpeg Ken Burns effect.

Endpoint: https://router.huggingface.co/hf-inference/models/{model}
Auth:     Authorization: Bearer {HUGGINGFACE_TOKEN}
Free tier: ~1000 requests/month, no credit card, just email signup.

Get token: huggingface.co → Settings → Access Tokens → New token (Read)
Set env:   HUGGINGFACE_TOKEN=hf_xxxxxxxxxxxx

Usage: generate_clip(image_prompt, clip_path, duration_s, api_key, effect_index)
"""

import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import HF_MODEL, HF_HEIGHT, HF_WIDTH, IMAGE_HEIGHT, IMAGE_WIDTH, KEN_BURNS_FPS

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

_HF_BASE = "https://router.huggingface.co/hf-inference/models"
_TIMEOUT_S = 300  # 5 min max per image

_KB_EFFECTS = [
    "zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
    "zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
    "zoompan=z='1.2':x='iw*0.1*on/{d}':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
    "zoompan=z='1.2':x='iw*0.1*(1-on/{d})':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
]


def generate_image(prompt: str, image_path: str, api_key: str) -> None:
    url = f"{_HF_BASE}/{HF_MODEL}"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"width": HF_WIDTH, "height": HF_HEIGHT}}

    deadline = time.time() + _TIMEOUT_S
    while time.time() < deadline:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)

        if resp.status_code == 200:
            if "image" in resp.headers.get("content-type", ""):
                with open(image_path, "wb") as f:
                    f.write(resp.content)
                return
            raise RuntimeError(f"200 but not an image: {resp.text[:200]}")

        if resp.status_code == 503:
            try:
                wait = float(resp.json().get("estimated_time", 20))
            except Exception:
                wait = 20
            wait = min(wait, 30)
            print(f"           model loading, retrying in {wait:.0f}s...")
            time.sleep(wait)
            continue

        if resp.status_code == 429:
            print("           rate limited, waiting 30s...")
            time.sleep(30)
            continue

        resp.raise_for_status()

    raise TimeoutError(f"HF generation timed out after {_TIMEOUT_S}s")


def apply_ken_burns(image_path: str, clip_path: str, duration_s: float, effect_index: int | None = None) -> None:
    total_frames = max(1, int(duration_s * KEN_BURNS_FPS))
    idx = effect_index if effect_index is not None else random.randint(0, len(_KB_EFFECTS) - 1)
    vf = _KB_EFFECTS[idx % len(_KB_EFFECTS)].format(
        d=total_frames, w=IMAGE_WIDTH, h=IMAGE_HEIGHT, fps=KEN_BURNS_FPS,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", image_path,
            "-vf", f"{vf},format=yuv420p",
            "-t", str(duration_s),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            clip_path,
        ],
        check=True, capture_output=True,
    )


def generate_clip(
    image_prompt: str,
    clip_path: str,
    api_key: str,
    duration_s: float,
    effect_index: int | None = None,
) -> str:
    """Generates image via HF, applies Ken Burns, returns image path."""
    image_path = clip_path.replace(".mp4", "_src.jpg")
    if not os.path.exists(image_path):
        generate_image(image_prompt, image_path, api_key)
    apply_ken_burns(image_path, clip_path, duration_s, effect_index)
    return image_path
