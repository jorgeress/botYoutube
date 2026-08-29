"""
Nano Banana (Gemini 2.5 Flash Image) backend.

Generates one still image per beat from a natural-language prompt, optionally
conditioned on a character reference image for cross-beat consistency, then
reuses the shared fade-clip builder so the rest of the pipeline is unchanged.

Free tier: ~193 images/day, no credit card. Get a key at https://aistudio.google.com
and set it in the GEMINI_API_KEY environment variable.

Install: pip install google-genai pillow
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import GEMINI_MODEL, GEMINI_MAX_RETRIES

# Reuse the exact fade + h264_nvenc (CPU fallback) clip builder used by the
# ComfyUI path so every backend produces identical clip encoding.
from scripts._comfyui import create_clip

try:
    from google import genai
    from PIL import Image
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False


_client = None  # lazily created, reused across calls


def _get_client(api_key: str):
    global _client
    if _client is None:
        _client = genai.Client(api_key=api_key)
    return _client


def _is_rate_limit(err: Exception) -> bool:
    s = str(err).lower()
    return "429" in s or "resource_exhausted" in s or "rate" in s or "quota" in s


def generate_image(prompt: str, out_png: str, api_key: str,
                   reference_png: str | None = None,
                   model: str | None = None) -> str:
    """
    Generate a single image and save it to out_png. Retries with exponential
    backoff on rate-limit / transient errors. Raises on permanent failure so the
    caller leaves the beat unmarked and retries on the next run.
    """
    if not _GENAI_AVAILABLE:
        raise RuntimeError(
            "google-genai / pillow not installed. Run: pip install google-genai pillow"
        )
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is empty, set the environment variable.")

    client   = _get_client(api_key)
    model_id = model or GEMINI_MODEL

    contents: list = [prompt]
    if reference_png and os.path.exists(reference_png):
        contents.append(Image.open(reference_png))

    last_err: Exception | None = None
    for attempt in range(GEMINI_MAX_RETRIES):
        try:
            resp = client.models.generate_content(model=model_id, contents=contents)
            for part in resp.parts:
                if getattr(part, "inline_data", None) is not None:
                    part.as_image().save(out_png)
                    return out_png
            # No image came back: surface any text the model returned for debugging.
            text = " ".join(getattr(p, "text", "") or "" for p in resp.parts).strip()
            raise RuntimeError(f"no image in response{f': {text[:120]}' if text else ''}")
        except Exception as e:  # noqa: BLE001, backoff on anything transient
            last_err = e
            if attempt < GEMINI_MAX_RETRIES - 1 and _is_rate_limit(e):
                wait = 2 ** attempt * 5  # 5s, 10s, 20s, ...
                print(f"           rate-limited, backing off {wait}s "
                      f"(attempt {attempt + 1}/{GEMINI_MAX_RETRIES})")
                time.sleep(wait)
                continue
            if attempt < GEMINI_MAX_RETRIES - 1:
                time.sleep(3)
                continue
            break

    raise RuntimeError(f"Gemini image generation failed: {last_err}")


def generate_clip(prompt: str, clip_path: str, api_key: str,
                  duration_s: float, effect_index: int = 0,
                  reference_png: str | None = None) -> str:
    """
    Generate the source image via Nano Banana, then build the timed fade clip.
    Returns the path to the saved source PNG (seg_NNN_src.png).
    effect_index is accepted for signature parity with other backends (unused,
    these are static illustrated frames, no Ken Burns).
    """
    src_png = clip_path.replace(".mp4", "_src.png")
    generate_image(prompt, src_png, api_key, reference_png=reference_png)
    create_clip(src_png, clip_path, duration_s)
    return src_png
