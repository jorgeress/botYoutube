"""
Leonardo.ai image generation + FFmpeg Ken Burns effect → MP4 clip.

  1. POST to Leonardo API to start generation
  2. Poll until complete, download the image
  3. Apply one of 4 Ken Burns effects via FFmpeg zoompan (duration is caller-supplied)
  4. Save as seg_XXX.mp4

Env var required: LEONARDO_API_KEY
"""

import os
import random
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import KEN_BURNS_FPS, LEONARDO_IMAGE_HEIGHT, LEONARDO_IMAGE_WIDTH, LEONARDO_MODEL_ID

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)

LEONARDO_BASE = "https://cloud.leonardo.ai/api/rest/v1"
POLL_INTERVAL_S = 4
POLL_TIMEOUT_S = 120

# 4 Ken Burns variants: rotate across clips for variety
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


def generate_image(prompt: str, api_key: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "modelId": LEONARDO_MODEL_ID,
        "num_images": 1,
        "width": LEONARDO_IMAGE_WIDTH,
        "height": LEONARDO_IMAGE_HEIGHT,
        "public": False,
    }
    resp = requests.post(f"{LEONARDO_BASE}/generations", json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["sdGenerationJob"]["generationId"]


def poll_generation(generation_id: str, api_key: str) -> str:
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        resp = requests.get(f"{LEONARDO_BASE}/generations/{generation_id}", headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("generations_by_pk", {})
        status = data.get("status")
        if status == "COMPLETE":
            images = data.get("generated_images", [])
            if not images:
                raise RuntimeError("Generation complete but no images returned.")
            return images[0]["url"]
        if status == "FAILED":
            raise RuntimeError(f"Leonardo generation failed: {data}")
        time.sleep(POLL_INTERVAL_S)
    raise TimeoutError(f"Leonardo generation timed out after {POLL_TIMEOUT_S}s")


def download_image(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                f.write(chunk)


def apply_ken_burns(image_path: str, clip_path: str, duration_s: float, effect_index: int | None = None) -> None:
    total_frames = max(1, int(duration_s * KEN_BURNS_FPS))
    idx = effect_index if effect_index is not None else random.randint(0, len(_KB_EFFECTS) - 1)
    vf = _KB_EFFECTS[idx % len(_KB_EFFECTS)].format(
        d=total_frames,
        w=LEONARDO_IMAGE_WIDTH,
        h=LEONARDO_IMAGE_HEIGHT,
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
    api_key: str,
    duration_s: float,
    effect_index: int | None = None,
) -> str:
    """Full pipeline: prompt → image → Ken Burns clip. Returns the image path."""
    image_path = clip_path.replace(".mp4", "_src.jpg")

    if not os.path.exists(image_path):
        generation_id = generate_image(image_prompt, api_key)
        image_url = poll_generation(generation_id, api_key)
        download_image(image_url, image_path)

    apply_ken_burns(image_path, clip_path, duration_s, effect_index)
    return image_path
