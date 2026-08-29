"""
Generates video clips from image_prompts.json.

Sources (CLIP_SOURCE in config.py):
  "leonardo": AI image via Leonardo.ai + Ken Burns effect  (env: LEONARDO_API_KEY)
  "pexels": stock footage search + trim to duration       (env: PEXELS_API_KEY)

Resumes automatically: entries with "generated": true are skipped.
Progress is saved to image_prompts.json after each successful clip.

Usage:
    python scripts/generate_clips.py [slug]
"""

import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    CLIP_SOURCE, OUTPUT_DIR, COMFYUI_URL,
    GEMINI_REQUEST_DELAY_S, CHARACTER_REFERENCE_IMAGE,
    IMAGE_WIDTH, IMAGE_HEIGHT,
)


def _beat_has_character(entry: dict) -> bool:
    """True if the beat's structured fields declare at least one character."""
    fields = entry.get("fields") or {}
    char_val = str(fields.get("char", "0")).split(",")[0].strip()
    try:
        return int(char_val) >= 1
    except ValueError:
        return False


def _create_manual_clip(src_png: str, clip_path: str, duration_s: float) -> None:
    """
    Build a timed fade clip from a hand-supplied image (manual / AI Studio route).
    Scales to cover 16:9 and center-crops, so square or off-ratio downloads fill the
    frame without distortion. Falls back to CPU encoder if nvenc is unavailable.
    """
    fade = min(0.05, duration_s / 3)
    fade_out = max(0.0, duration_s - fade)
    vf = (
        f"scale={IMAGE_WIDTH}:{IMAGE_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={IMAGE_WIDTH}:{IMAGE_HEIGHT},"
        f"fade=t=in:st=0:d={fade:.3f},fade=t=out:st={fade_out:.3f}:d={fade:.3f},"
        f"format=yuv420p"
    )
    base = ["ffmpeg", "-y", "-loop", "1", "-i", src_png, "-vf", vf, "-t", str(duration_s)]
    try:
        subprocess.run(base + ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", clip_path],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        err = e.stderr.decode(errors="replace") if e.stderr else ""
        if "nvenc" in err or "CUDA" in err or "cuInit" in err:
            subprocess.run(base + ["-c:v", "libopenh264", "-b:v", "2M", clip_path],
                           check=True, capture_output=True)
        else:
            raise

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests")
    sys.exit(1)


# ── Pexels helpers ─────────────────────────────────────────────────────────────

from config import PEXELS_VIDEO_MIN_DURATION, PEXELS_VIDEO_ORIENTATION

_NOISE = {
    "cinematic", "4k", "dramatic", "lighting", "shadows", "atmospheric",
    "close", "up", "wide", "shot", "angle", "slow", "camera", "movement",
    "photorealistic", "aesthetic", "style", "low", "key", "extreme",
    "side", "high", "contrast", "footage", "video", "clip", "scene",
    "simple", "stickman", "illustration", "stick", "figures", "white",
    "background", "minimal", "line", "art", "flat", "shading", "texture",
    "clean", "drawing", "2d", "no", "people", "faces", "logos", "text",
}


def _pexels_keywords(visual_prompt: str) -> str:
    parts = re.split(r"[,.]", visual_prompt)
    words: list[str] = []
    for part in parts[:3]:
        for w in part.strip().lower().split():
            if w not in _NOISE and len(w) > 2:
                words.append(w)
        if len(words) >= 4:
            break
    return " ".join(words[:4]) if words else visual_prompt[:40]


def _pexels_search(query: str, api_key: str) -> list[dict]:
    resp = requests.get(
        "https://api.pexels.com/videos/search",
        headers={"Authorization": api_key},
        params={"query": query, "per_page": 10, "orientation": PEXELS_VIDEO_ORIENTATION},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("videos", [])


def _pexels_best_file(video: dict) -> dict | None:
    files = [f for f in video.get("video_files", []) if f.get("file_type") == "video/mp4"]
    hd = [f for f in files if f.get("quality") in ("hd", "sd")]
    pool = hd or files
    return max(pool, key=lambda f: f.get("width", 0) * f.get("height", 0)) if pool else None


def _download(url: str, dest: str) -> None:
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                f.write(chunk)


def _get_pexels_clip(entry: dict, clip_path: str, api_key: str) -> bool:
    query = _pexels_keywords(entry["parent_visual_prompt"])
    print(f"           Pexels search: '{query}'")
    for q in [query, " ".join(query.split()[:2])]:
        videos = _pexels_search(q, api_key)
        videos = [v for v in videos if v.get("duration", 0) >= PEXELS_VIDEO_MIN_DURATION]
        if videos:
            break
    if not videos:
        return False
    best = _pexels_best_file(videos[0])
    if not best:
        return False

    raw = clip_path.replace(".mp4", "_raw.mp4")
    _download(best["link"], raw)

    # Trim to exact duration
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw, "-t", str(entry["duration_seconds"]),
         "-c:v", "libx264", "-preset", "fast", "-crf", "20",
         "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
         clip_path],
        check=True, capture_output=True,
    )
    os.remove(raw)
    return True


# ── Main ───────────────────────────────────────────────────────────────────────

def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders found in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def save_progress(prompts_path: str, entries: list[dict]) -> None:
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


def main():
    source = CLIP_SOURCE.lower()

    # ── ComfyUI: batch all images in one queue submission ─────────────────────
    if source == "comfyui":
        slug_arg = sys.argv[1] if len(sys.argv) > 1 else None
        slug     = find_slug(slug_arg)
        out_dir  = os.path.join(OUTPUT_DIR, slug)
        prompts_path = os.path.join(out_dir, "image_prompts.json")

        if not os.path.exists(prompts_path):
            print(f"ERROR: {prompts_path} not found. Run generate_image_prompts.py first.")
            sys.exit(1)

        with open(prompts_path, encoding="utf-8") as f:
            entries = json.load(f)

        clips_dir = os.path.join(out_dir, "clips")
        os.makedirs(clips_dir, exist_ok=True)

        from scripts._comfyui import generate_all_clips
        print(f"Generating clips [comfyui] for: {slug}")
        generate_all_clips(entries, clips_dir)

        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        done = sum(1 for e in entries if e.get("generated"))
        print(f"\n{done}/{len(entries)} clips done.")
        return

    api_key = None
    if source == "manual":
        pass  # no API: images are supplied by hand as clips/seg_NNN_src.png
    elif source == "gemini":
        from config import GEMINI_API_KEY as _CFG_GEMINI_KEY
        api_key = (os.environ.get("GEMINI_API_KEY", "")
                   or os.environ.get("GOOGLE_API_KEY", "")
                   or _CFG_GEMINI_KEY).strip()
        if not api_key:
            print("ERROR: No Gemini API key. Set GEMINI_API_KEY env var "
                  "or GEMINI_API_KEY in config.py.")
            print("  Get a free key (no card) at https://aistudio.google.com")
            sys.exit(1)
    elif source == "huggingface":
        api_key = os.environ.get("HUGGINGFACE_TOKEN", "").strip()
        if not api_key:
            print("ERROR: Set HUGGINGFACE_TOKEN environment variable.")
            print("  Get a free token at https://huggingface.co/settings/tokens")
            sys.exit(1)
    elif source == "pollinations":
        pass  # no key needed
    elif source == "pexels":
        api_key = os.environ.get("PEXELS_API_KEY", "").strip()
        if not api_key:
            print("ERROR: Set PEXELS_API_KEY environment variable.")
            sys.exit(1)
    elif source == "leonardo":
        api_key = os.environ.get("LEONARDO_API_KEY", "").strip()
        if not api_key:
            print("ERROR: Set LEONARDO_API_KEY environment variable.")
            print("  Get a free key at https://app.leonardo.ai/")
            sys.exit(1)
    else:
        print(f"ERROR: Unknown CLIP_SOURCE '{source}'. "
              "Use 'gemini', 'manual', 'comfyui', 'huggingface', 'pexels', or 'leonardo'.")
        sys.exit(1)

    slug_arg = sys.argv[1] if len(sys.argv) > 1 else None
    slug = find_slug(slug_arg)
    out_dir = os.path.join(OUTPUT_DIR, slug)
    prompts_path = os.path.join(out_dir, "image_prompts.json")

    if not os.path.exists(prompts_path):
        print(f"ERROR: {prompts_path} not found. Run generate_image_prompts.py first.")
        sys.exit(1)

    with open(prompts_path, encoding="utf-8") as f:
        entries = json.load(f)

    clips_dir = os.path.join(out_dir, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    total = len(entries)
    done = sum(1 for e in entries if e.get("generated"))
    print(f"Generating clips [{source}], {total - done} remaining of {total}")

    for entry in entries:
        if entry.get("generated"):
            continue

        idx = str(entry["index"]).zfill(3)
        clip_path = os.path.join(clips_dir, f"seg_{idx}.mp4")
        duration_s = entry["duration_seconds"]
        narration = entry.get("narration", entry.get("narration_text", ""))
        print(f"  seg_{idx} ({duration_s:.1f}s): {narration[:55]}...")

        try:
            if source == "manual":
                # Image was generated by hand (AI Studio) and saved as seg_NNN_src.png.
                src_png = clip_path.replace(".mp4", "_src.png")
                if not os.path.exists(src_png):
                    print(f"           no image yet ({os.path.basename(src_png)}), "
                          f"generate it in AI Studio and save it here; skipping for now")
                    continue
                _create_manual_clip(src_png, clip_path, duration_s)
                entry["image_path"] = src_png
            elif source == "gemini":
                from scripts._gemini import generate_clip
                prompt = entry.get("image_prompt", "").strip()
                if not prompt:
                    print(f"           empty prompt: re-run generate_image_prompts.py "
                          f"--force with CLIP_SOURCE=gemini, skipping")
                    continue
                # Pass the character reference only on beats that have a character,
                # so it does not inject a stickman into object/diagram/text frames.
                ref = CHARACTER_REFERENCE_IMAGE if _beat_has_character(entry) else None
                image_path = generate_clip(
                    prompt, clip_path, api_key,
                    duration_s=duration_s, reference_png=ref,
                )
                entry["image_path"] = image_path
                time.sleep(GEMINI_REQUEST_DELAY_S)  # throttle for the free-tier RPM limit
            elif source == "huggingface":
                from scripts._huggingface import generate_clip
                image_path = generate_clip(
                    entry["image_prompt"],
                    clip_path,
                    api_key,
                    duration_s=duration_s,
                    effect_index=entry["index"] % 4,
                )
                entry["image_path"] = image_path
            elif source == "pollinations":
                from scripts._pollinations import generate_clip
                image_path = generate_clip(
                    entry["image_prompt"],
                    clip_path,
                    duration_s=duration_s,
                    effect_index=entry["index"] % 4,
                )
                entry["image_path"] = image_path
            elif source == "leonardo":
                from scripts._leonardo import generate_clip
                image_path = generate_clip(
                    entry["image_prompt"],
                    clip_path,
                    api_key,
                    duration_s=duration_s,
                    effect_index=entry["index"] % 4,
                )
                entry["image_path"] = image_path
            else:
                ok = _get_pexels_clip(entry, clip_path, api_key)
                if not ok:
                    print(f"           no Pexels result, skipping")
                    continue

            entry["generated"] = True
            save_progress(prompts_path, entries)
            size_kb = os.path.getsize(clip_path) // 1024
            print(f"           saved ({size_kb} KB)")

        except Exception as e:
            print(f"           ERROR: {e}")
            # Don't mark as generated: will retry on next run

    done_now = sum(1 for e in entries if e.get("generated"))
    remaining = total - done_now
    if remaining:
        print(f"\n{done_now}/{total} clips done. {remaining} remaining, re-run to continue.")
    else:
        print(f"\nAll {total} clips done.")


if __name__ == "__main__":
    main()
