"""
Style test v4: both styles A and B across 6 varied specific scenes.
Tests how well each style handles different contexts: domestic, action,
nature, social, emotional: the kind of scenes that appear in narration.

Style A: white bg hand-drawn stickman (relaxed color palette)
Style B: dark bg Kurzgesagt-inspired stickman

2 styles x 6 scenes = 12 images at 1024x576

Output: C:\\dev\\ComfyUI\\output\\v4_<style>_<scene>_*.png
"""

import json
import sys
import time
import urllib.request

COMFY_URL = "http://localhost:8188"
WIDTH  = 1024
HEIGHT = 576
STEPS  = 4
SEED   = 3001

# ── Style A: white background, hand-drawn, relaxed colors ───────────────────
STYLE_A = (
    "hand-drawn 2D animation YouTube style, pure white background, "
    "imperfect slightly wobbly black ink outlines, not clean vector, "
    "stickman human characters with circular heads, dot eyes, simple curved mouth, thin stick limbs, "
    "flat color fills on objects and environment, warm colors for indoor scenes, "
    "simple readable props with some detail, thin brown ground line or simple floor, "
    "educational explainer animation feel, muted earthy tones"
)
ANTI_A = "no photorealism, no 3D, no gradients, no shading, no dark background, no realistic anatomy"

# ── Style B: dark bg, bold colors, Kurzgesagt-inspired ──────────────────────
STYLE_B = (
    "2D flat animation, stickman characters with circular heads and thin limbs, "
    "dot eyes and small curved mouth on all characters, "
    "scene environment in flat color blocks with dark muted background, "
    "bright bold accent colors for characters and key props (orange, teal, yellow, red), "
    "thick consistent black outlines, Kurzgesagt-inspired illustration, cinematic wide shot"
)
ANTI_B = "no gradients, no textures, no photorealism, no 3D, no realistic anatomy, no white background"

# ── Scenes: varied, specific, narrative-driven ───────────────────────────────
SCENES = {
    "soup_worried": (
        "a stickman man sitting alone at a kitchen table, hunched over a steaming bowl of soup, "
        "his expression worried and sad, one hand on his forehead, "
        "simple kitchen background with a window, evening light"
    ),
    "man_painting": (
        "a stickman man standing in front of a large canvas on an easel, "
        "holding a paintbrush, colorful paint splatters on the canvas, "
        "paint bucket on the floor beside him, focused and happy expression"
    ),
    "predator_prey": (
        "a large wolf or lion stickman-style animal pouncing on a smaller deer or rabbit, "
        "mid-air attack scene, motion lines, outdoor grassy setting, "
        "dramatic action pose, both animals clearly drawn in the same hand-drawn style"
    ),
    "office_argument": (
        "two stickman figures facing each other in an office, both angry expressions, "
        "one pointing a finger, the other with arms crossed, "
        "simple desk and computer in background, tense confrontational body language"
    ),
    "night_reading": (
        "a stickman person sitting in an armchair reading a book, "
        "single lamp beside them casting warm light in a dark room, "
        "cozy quiet atmosphere, cat curled up at their feet, "
        "bookshelves in the background, peaceful expression"
    ),
    "crowd_watching": (
        "a crowd of small stickman figures standing and looking up at a large screen or projector, "
        "the screen showing a simple graph or image, "
        "auditorium or conference room setting, rows of seats visible, "
        "varied expressions of interest and concern among the audience"
    ),
}


def check_comfy() -> bool:
    try:
        urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=3)
        return True
    except Exception:
        return False


def free_vram() -> None:
    try:
        body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
        req  = urllib.request.Request(f"{COMFY_URL}/free", data=body,
                                       headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        time.sleep(1)
    except Exception:
        pass


def build_workflow(prompt: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF",  "inputs": {"unet_name": "flux1-schnell-Q4_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader",   "inputs": {
            "clip_name1": "clip_l.safetensors",
            "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
            "type": "flux",
        }},
        "3": {"class_type": "VAELoader",        "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode",   "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode",   "inputs": {"clip": ["2", 0], "text": ""}},
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["6", 0], "seed": SEED, "steps": STEPS,
            "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
        }},
        "8": {"class_type": "VAEDecode",  "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",  "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
    }


def submit(workflow: dict) -> str:
    body = json.dumps({"prompt": workflow}).encode("utf-8")
    req  = urllib.request.Request(f"{COMFY_URL}/prompt", data=body,
                                   headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=15).read())["prompt_id"]


def wait(pid: str, timeout: int = 300) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3)
        try:
            hist = json.loads(urllib.request.urlopen(
                f"{COMFY_URL}/history/{pid}", timeout=10).read())
            if pid in hist and hist[pid]["status"].get("completed"):
                outputs = hist[pid]["outputs"]
                return outputs[next(iter(outputs))]["images"][0]["filename"]
        except Exception:
            pass
    raise TimeoutError(f"timed out after {timeout}s")


def run_style(style_key: str, style_prompt: str, anti: str, results: list, idx_start: int) -> int:
    idx = idx_start
    total_per_style = len(SCENES)
    for scene_key, scene_desc in SCENES.items():
        full_prompt = f"{style_prompt}, {scene_desc}, no text overlays, no watermarks, {anti}"
        prefix = f"v4_{style_key}_{scene_key}"
        print(f"  [{idx:02d}] {style_key} x {scene_key}")
        print(f"       {full_prompt[:100]}...")
        free_vram()
        try:
            pid   = submit(build_workflow(full_prompt, prefix))
            fname = wait(pid)
            print(f"       -> {fname}\n")
            results.append((style_key, scene_key, fname, True))
        except Exception as e:
            print(f"       ERROR: {e}\n")
            results.append((style_key, scene_key, None, False))
        idx += 1
    return idx


def main():
    if not check_comfy():
        print("ERROR: ComfyUI not running at http://localhost:8188")
        sys.exit(1)

    total = 2 * len(SCENES)
    print(f"Style test v4: 2 styles x {len(SCENES)} scenes = {total} images")
    print(f"Seed: {SEED} (fixed) | {WIDTH}x{HEIGHT}\n")
    print("-- Style A (white bg, hand-drawn, relaxed colors) ----------")

    results = []
    idx = run_style("styleA", STYLE_A, ANTI_A, results, 1)

    print("-- Style B (dark bg, Kurzgesagt-inspired) ------------------")
    run_style("styleB", STYLE_B, ANTI_B, results, idx)

    ok = sum(1 for r in results if r[3])
    print(f"-- Done: {ok}/{total} generated. Files: C:\\dev\\ComfyUI\\output\\v4_*.png")
    print("\nCompare style A vs B for each scene:")
    for sk in SCENES:
        a = next((r[2] for r in results if r[0] == "styleA" and r[1] == sk and r[3]), "FAILED")
        b = next((r[2] for r in results if r[0] == "styleB" and r[1] == sk and r[3]), "FAILED")
        print(f"  {sk:<22}  A: {a or 'FAILED':<45}  B: {b or 'FAILED'}")


if __name__ == "__main__":
    main()
