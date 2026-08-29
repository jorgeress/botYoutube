"""
Pollinations.ai image generation + FFmpeg Ken Burns effect → MP4 clip.

No API key, no account, no cost.
GET https://image.pollinations.ai/prompt/{encoded_prompt}?width=W&height=H&model=flux&nologo=true
Response body is the image in binary (PNG/JPEG).

Usage: call generate_clip(image_prompt, clip_path, duration_s, effect_index)
"""

import os
import random
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import IMAGE_HEIGHT, IMAGE_WIDTH, KEN_BURNS_FPS, POLLINATIONS_HEIGHT, POLLINATIONS_MODEL, POLLINATIONS_WIDTH

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

_POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

_KB_EFFECTS = [
    # slow zoom in from center
    "zoompan=z='min(zoom+0.0015,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
    # slow zoom out from center
    "zoompan=z='if(lte(zoom,1.0),1.3,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
    # pan left to right
    "zoompan=z='1.2':x='iw*0.1*on/{d}':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
    # pan right to left
    "zoompan=z='1.2':x='iw*0.1*(1-on/{d})':y='ih/2-(ih/zoom/2)':d={d}:s={w}x{h}:fps={fps}",
]


def generate_image(prompt: str, image_path: str) -> None:
    encoded = urllib.parse.quote(prompt, safe="")
    params = f"?width={POLLINATIONS_WIDTH}&height={POLLINATIONS_HEIGHT}"
    if POLLINATIONS_MODEL:
        params += f"&model={POLLINATIONS_MODEL}"
    url = f"{_POLLINATIONS_BASE}/{encoded}{params}"
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    with open(image_path, "wb") as f:
        f.write(resp.content)


def apply_ken_burns(image_path: str, clip_path: str, duration_s: float, effect_index: int | None = None) -> None:
    total_frames = max(1, int(duration_s * KEN_BURNS_FPS))
    idx = effect_index if effect_index is not None else random.randint(0, len(_KB_EFFECTS) - 1)
    vf = _KB_EFFECTS[idx % len(_KB_EFFECTS)].format(
        d=total_frames,
        w=IMAGE_WIDTH,
        h=IMAGE_HEIGHT,
        fps=KEN_BURNS_FPS,
    )
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-vf", f"{vf},format=yuv420p",
            "-t", str(duration_s),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            clip_path,
        ],
        check=True,
        capture_output=True,
    )


def generate_clip(
    image_prompt: str,
    clip_path: str,
    duration_s: float,
    effect_index: int | None = None,
) -> str:
    """Generates image from Pollinations, applies Ken Burns, returns image path."""
    image_path = clip_path.replace(".mp4", "_src.jpg")
    if not os.path.exists(image_path):
        generate_image(image_prompt, image_path)
    apply_ken_burns(image_path, clip_path, duration_s, effect_index)
    return image_path
