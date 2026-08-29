"""
Style refinement v3: based on reference image analysis.
Tests the corrected white-background hand-drawn stickman style
with 4 prompt variants across 3 scenes = 12 images.

Key corrections from v2:
- WHITE background (not dark/navy: that was wrong)
- Hand-drawn wobbly lines, not clean vector
- Minimal palette: black, grey, warm brown, occasional yellow/red
- Simple readable compositions with lots of white space
- Stickman humans (not Kurzgesagt flat blocks)

Output: C:\\dev\\ComfyUI\\output\\v3_<variant>_<scene>_*.png
"""

import json
import sys
import time
import urllib.request

COMFY_URL = "http://localhost:8188"
WIDTH  = 1024
HEIGHT = 576
STEPS  = 4
SEED   = 2024  # fixed, differences come only from prompt

# ── Style variants: all white background stickman, testing nuances ───────────
VARIANTS = {
    # Base: direct translation of what's in the reference images
    "v1_base": (
        "simple hand-drawn 2D animation, pure white background, "
        "thin black hand-drawn outlines with slight natural wobble, "
        "stickman human figures with circular heads, small dot eyes, simple curved mouth, thin stick limbs, "
        "minimal flat color fills using only grey and warm brown, "
        "thin flat warm brown ground strip at bottom, lots of white space, "
        "educational YouTube explainer animation style"
    ),
    # Emphasize the hand-drawn sketch quality more
    "v2_sketch": (
        "hand-drawn sketch animation style, white background, "
        "black ink lines with organic imperfect wobble like drawn by hand, "
        "stick figure people with round circle heads, tiny dot eyes, small mouth, thin limbs, "
        "simple flat grey or brown fills on clothing and ground, no shading, "
        "minimal props, wide empty white space around subjects, "
        "simple YouTube educational video illustration"
    ),
    # More explicit stickman + crime scene objects for true crime content
    "v3_crime_adapted": (
        "simple 2D hand-drawn YouTube animation, clean white background, "
        "stickman characters with circular heads, dot eyes and small curved mouth, thin line body, "
        "simple iconic objects drawn in the same hand-drawn black outline style, "
        "grey flat fills for characters, warm brown for floor surface, "
        "occasional red accent for important elements, "
        "readable at a glance, educational explainer video aesthetic"
    ),
    # Test how well it handles multiple characters (crowd/group scenes)
    "v4_minimal_crowd": (
        "minimalist hand-drawn 2D animation frame, pure white background, "
        "multiple small stickman figures with round heads and dot eyes arranged in scene, "
        "all characters same consistent thin black line style, simple grey fills, "
        "flat brown ground line at bottom of frame, clean composition, "
        "no backgrounds, no textures, no shading, sketch animation style"
    ),
}

# ── Scenes adapted for true crime/horror with this white-bg stickman style ────
SCENES = {
    # Two stickmen, simple room implied by ground line
    "interrogation": (
        "two stickman figures sitting across a simple rectangular table, "
        "one pointing finger at the other, single overhead lamp above the table, "
        "simple sparse room with just the ground and table as props"
    ),
    # Group of stickmen behind a line/barrier, simple city implied
    "crime_scene": (
        "several stickman figures standing behind a horizontal police tape line, "
        "two stickmen in front crouching to examine the ground, "
        "simple rectangular building shapes in the background"
    ),
    # Single stickman figure running, trees as simple vertical lines
    "chase": (
        "one stickman figure running at full speed, arms and legs mid-stride, "
        "several simple vertical brown tree trunks on either side, "
        "motion lines behind the running figure, minimal background"
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


def build_workflow(prompt_text: str, prefix: str) -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF",  "inputs": {"unet_name": "flux1-schnell-Q4_K_S.gguf"}},
        "2": {"class_type": "DualCLIPLoader",   "inputs": {
            "clip_name1": "clip_l.safetensors",
            "clip_name2": "t5xxl_fp8_e4m3fn.safetensors",
            "type": "flux",
        }},
        "3": {"class_type": "VAELoader",        "inputs": {"vae_name": "ae.safetensors"}},
        "4": {"class_type": "CLIPTextEncode",   "inputs": {"clip": ["2", 0], "text": prompt_text}},
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


def main():
    if not check_comfy():
        print("ERROR: ComfyUI not running at http://localhost:8188")
        sys.exit(1)

    total = len(VARIANTS) * len(SCENES)
    print(f"Style test v3 (white-bg stickman): {len(VARIANTS)} variants x {len(SCENES)} scenes = {total} images")
    print(f"Seed: {SEED} (fixed) | Resolution: {WIDTH}x{HEIGHT}\n")

    results = []
    idx = 1
    for vk, vstyle in VARIANTS.items():
        for sk, sscene in SCENES.items():
            prompt = (
                f"{vstyle}, {sscene}, "
                "no text overlays, no watermarks, no logos, no realistic style"
            )
            prefix = f"v3_{vk}_{sk}"
            print(f"  [{idx:02d}/{total}] {vk} x {sk}")
            print(f"         {prompt[:110]}...")
            free_vram()
            try:
                pid  = submit(build_workflow(prompt, prefix))
                fname = wait(pid)
                print(f"         -> {fname}\n")
                results.append((vk, sk, fname, True))
            except Exception as e:
                print(f"         ERROR: {e}\n")
                results.append((vk, sk, None, False))
            idx += 1

    ok = sum(1 for r in results if r[3])
    print("-- Summary " + "-" * 60)
    print(f"{ok}/{total} generated. Files in C:\\dev\\ComfyUI\\output\\ (v3_*.png)")
    print("\nLook for: which variant best matches the reference style?")
    print("  v1_base       = direct translation")
    print("  v2_sketch     = more hand-drawn emphasis")
    print("  v3_crime_adapted = adapted for true crime objects")
    print("  v4_minimal_crowd = focus on consistent multi-character groups")


if __name__ == "__main__":
    main()
