"""
Local ComfyUI image generation + Ken Burns effect.

Strategy: submit ALL prompts to ComfyUI queue at once so the GGUF model
loads only one time. Then poll until each finishes and apply Ken Burns.
This avoids the ~15s model-reload penalty that happens when generating one-by-one.

Requires ComfyUI running at http://localhost:8188 (no --highvram flag).
Start: cd C:\\dev\\ComfyUI && python main.py --port 8188
"""

import json
import os
import random
import subprocess
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    COMFYUI_URL,
    COMFYUI_WIDTH, COMFYUI_HEIGHT,
    COMFYUI_UNET, COMFYUI_CLIP1, COMFYUI_CLIP2, COMFYUI_VAE,
    COMFYUI_STEPS, COMFYUI_BATCH_SIZE,
    IMAGE_WIDTH, IMAGE_HEIGHT,
)
try:
    from scripts._text_frame import render_text_frame as _render_tf, extract_frame_text as _extract_tf_text
    _TEXT_FRAME_AVAILABLE = True
except Exception:
    _TEXT_FRAME_AVAILABLE = False

try:
    from scripts._diagram_frame import render_diagram_frame as _render_df, can_render as _df_can_render
    _DIAGRAM_FRAME_AVAILABLE = True
except Exception:
    _DIAGRAM_FRAME_AVAILABLE = False

try:
    from scripts._sprites import composite_sprites as _composite_sprites, composite_place_label as _composite_place
    _SPRITES_AVAILABLE = True
except Exception:
    _SPRITES_AVAILABLE = False

_FADE_DUR = 0.05  # seconds fade-in and fade-out on each clip, 50ms each side = ~2 frames, barely perceptible


def _apply_post_effects(src_img: str, entry: dict) -> None:
    """
    Apply PIL post-processing to a generated image (Flux or PIL-rendered):
      1. Sprite compositing (_sprites.composite_sprites)
      2. Place label overlay (_sprites.composite_place_label) for beats with place:
    Modifies src_img in place. Silently skipped if modules or assets unavailable.
    """
    if not _SPRITES_AVAILABLE:
        return
    seed    = entry.get("seed", 0)
    sprites = entry.get("_sprites", [])
    if sprites:
        try:
            _composite_sprites(src_img, sprites, seed, IMAGE_WIDTH, IMAGE_HEIGHT)
        except Exception as ex:
            print(f"    sprite compositing failed: {ex}")

    fields = entry.get("fields") or {}
    place_val = fields.get("place", "").strip("'\"")
    if place_val:
        try:
            from config import FONT_PATHS_BOLD
            _composite_place(src_img, place_val, FONT_PATHS_BOLD)
        except Exception as ex:
            print(f"    place label failed: {ex}")


def check_comfyui() -> bool:
    try:
        urllib.request.urlopen(f"{COMFYUI_URL}/system_stats", timeout=5)
        return True
    except Exception:
        return False


def _build_workflow(prompt_text: str, prefix: str, seed: int) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": COMFYUI_UNET}},
        "2": {"class_type": "DualCLIPLoader", "inputs": {
            "clip_name1": COMFYUI_CLIP1,
            "clip_name2": COMFYUI_CLIP2,
            "type": "flux",
        }},
        "3": {"class_type": "VAELoader",      "inputs": {"vae_name": COMFYUI_VAE}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": prompt_text}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {
            "width": COMFYUI_WIDTH, "height": COMFYUI_HEIGHT, "batch_size": 1,
        }},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["6", 0], "seed": seed, "steps": COMFYUI_STEPS,
            "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "8": {"class_type": "VAEDecode",  "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",  "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def _submit(workflow: dict) -> str:
    body = json.dumps({"prompt": workflow}).encode("utf-8")
    req  = urllib.request.Request(
        f"{COMFYUI_URL}/prompt", data=body,
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["prompt_id"]


def _get_output_path(prompt_id: str, timeout: int = 300) -> str | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            hist = json.loads(urllib.request.urlopen(
                f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).read())
            if prompt_id not in hist:
                continue
            status = hist[prompt_id]["status"]
            if status.get("completed"):
                outputs = hist[prompt_id]["outputs"]
                node    = next(iter(outputs))
                img     = outputs[node]["images"][0]
                # ComfyUI saves to its own output dir
                return os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "..", "ComfyUI", "output", img["filename"],
                ).replace("/", os.sep)
            if status.get("status_str") == "error":
                return None
        except Exception:
            pass
    return None


def create_clip(image_path: str, clip_path: str, duration_s: float) -> None:
    fade_dur = min(_FADE_DUR, duration_s / 3)
    fade_out_start = max(0.0, duration_s - fade_dur)
    vf = (
        f"scale={IMAGE_WIDTH}:{IMAGE_HEIGHT}:flags=lanczos,"
        f"fade=t=in:st=0:d={fade_dur:.3f},"
        f"fade=t=out:st={fade_out_start:.3f}:d={fade_dur:.3f},"
        f"format=yuv420p"
    )
    base_args = ["ffmpeg", "-y", "-loop", "1", "-i", image_path, "-vf", vf, "-t", str(duration_s)]
    try:
        subprocess.run(
            base_args + ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20", clip_path],
            check=True, capture_output=True,
        )
    except subprocess.CalledProcessError as primary_err:
        # GPU lost / CUDA context invalid, fall back to CPU encoder
        stderr = primary_err.stderr.decode(errors="replace") if primary_err.stderr else ""
        if "cuInit" in stderr or "h264_nvenc" in stderr or "CUDA" in stderr:
            print(f"    WARNING: h264_nvenc failed (GPU lost?), retrying with libopenh264")
            subprocess.run(
                base_args + ["-c:v", "libopenh264", "-b:v", "2M", clip_path],
                check=True, capture_output=True,
            )
        else:
            raise


def generate_all_clips(entries: list[dict], clips_dir: str) -> None:
    """
    Generate all clips:
      - text_frame beats: PIL renderer (_text_frame.py), no ComfyUI
      - scene beats: ComfyUI (batched) + optional PIL overlay (_overlay.py)

    Disk-based resume: completed .mp4 clips are never regenerated.
    """
    # Disk-based resume: skip clips already on disk
    pending = []
    for e in entries:
        idx       = str(e["index"]).zfill(3)
        clip_path = os.path.join(clips_dir, f"seg_{idx}.mp4")
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
            e["generated"] = True
            e["image_path"] = clip_path.replace(".mp4", "_src.png")
        elif not e.get("generated"):
            pending.append(e)

    if not pending:
        print("  All clips already generated.")
        return

    # ── PIL-only beats (text_frame, diagram): no ComfyUI ────────────────────
    comfyui_pending = []
    for entry in pending:
        beat_type = entry.get("beat_type")
        has_empty_prompt = not entry.get("image_prompt", "").strip()

        if beat_type == "text_frame" and _TEXT_FRAME_AVAILABLE:
            idx       = str(entry["index"]).zfill(3)
            clip_path = os.path.join(clips_dir, f"seg_{idx}.mp4")
            src_img   = clip_path.replace(".mp4", "_src.png")
            try:
                _render_tf(entry["visual"], src_img, icon_top=bool(entry.get("_sprites")))
                _apply_post_effects(src_img, entry)
                create_clip(src_img, clip_path, entry["duration_seconds"])
                entry["generated"] = True
                entry["image_path"] = src_img
                size_kb = os.path.getsize(clip_path) // 1024
                text = _extract_tf_text(entry["visual"])
                print(f"  seg_{idx}: text_frame PIL [{text[:35]}] ({size_kb} KB)")
            except Exception as ex:
                print(f"  seg_{idx}: text_frame PIL failed ({ex}), falling back to ComfyUI")
                comfyui_pending.append(entry)

        elif beat_type == "diagram" and has_empty_prompt and _DIAGRAM_FRAME_AVAILABLE:
            idx       = str(entry["index"]).zfill(3)
            clip_path = os.path.join(clips_dir, f"seg_{idx}.mp4")
            src_img   = clip_path.replace(".mp4", "_src.png")
            try:
                from scripts.parse_script import parse_fields
                fields = entry.get("fields") or parse_fields(entry["visual"]) or {}
                _render_df(fields, src_img)
                _apply_post_effects(src_img, entry)
                create_clip(src_img, clip_path, entry["duration_seconds"])
                entry["generated"] = True
                entry["image_path"] = src_img
                size_kb = os.path.getsize(clip_path) // 1024
                left  = fields.get("left", "?")
                right = fields.get("right", "?")
                print(f"  seg_{idx}: diagram PIL [{left}->{right}] ({size_kb} KB)")
            except Exception as ex:
                print(f"  seg_{idx}: diagram PIL failed ({ex}), falling back to ComfyUI")
                comfyui_pending.append(entry)

        else:
            comfyui_pending.append(entry)

    if not comfyui_pending:
        return

    # ── scene beats: ComfyUI ─────────────────────────────────────────────────
    if not check_comfyui():
        raise RuntimeError(
            f"ComfyUI not running at {COMFYUI_URL}\n"
            "Start with: cd C:\\dev\\ComfyUI && python main.py --port 8188"
        )

    pending = comfyui_pending

    # Process in small batches: queue a few, wait for them, then queue more.
    # Bounds ComfyUI's working set so 8GB VRAM doesn't crash on long runs,
    # while still keeping the model resident between items in a batch.
    batch_size = max(1, COMFYUI_BATCH_SIZE)
    print(f"  {len(pending)} clips to render (batches of {batch_size})...\n")

    for b_start in range(0, len(pending), batch_size):
        batch = pending[b_start:b_start + batch_size]
        jobs: list[tuple[dict, str, str]] = []  # (entry, prompt_id, clip_path)

        for entry in batch:
            idx       = str(entry["index"]).zfill(3)
            clip_path = os.path.join(clips_dir, f"seg_{idx}.mp4")
            prefix    = f"clip_seg{idx}"
            seed      = entry.get("seed", random.randint(0, 2**32 - 1))
            pid       = _submit(_build_workflow(entry["image_prompt"], prefix, seed))
            jobs.append((entry, pid, clip_path))
            print(f"    queued seg_{idx} -> {pid[:8]}...")
            time.sleep(0.2)

        for entry, pid, clip_path in jobs:
            idx = str(entry["index"]).zfill(3)
            img_path = _get_output_path(pid)
            if img_path is None or not os.path.exists(img_path):
                print(f"  seg_{idx}: ERROR: ComfyUI returned no image")
                continue

            src_img = clip_path.replace(".mp4", "_src.png")
            if img_path != src_img:
                import shutil
                shutil.copy2(img_path, src_img)

            _apply_post_effects(src_img, entry)
            create_clip(src_img, clip_path, entry["duration_seconds"])
            entry["generated"] = True
            entry["image_path"] = src_img
            size_kb = os.path.getsize(clip_path) // 1024
            print(f"  seg_{idx}: OK ({size_kb} KB)")
