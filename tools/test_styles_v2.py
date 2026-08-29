"""
Style refinement test: Kurzgesagt/stickman 2D style variants
Generates prompt variations for the chosen style via ComfyUI local API.

Goal: find the best prompt formulation for Flux Schnell that consistently produces
clean Kurzgesagt-inspired stickman 2D animation for true crime/horror YouTube content.

6 prompt variants × 3 complex scenes = 18 images at 1024x576 (16:9)

Requires ComfyUI running at http://localhost:8188
Start with:
    $env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
    cd C:\\dev\\ComfyUI; python main.py --port 8188 --highvram

Output: C:\\dev\\ComfyUI\\output\\v2_<variant>_<scene>_*.png
"""

import json
import time
import urllib.request
import sys

COMFY_URL = "http://localhost:8188"
WIDTH  = 1024
HEIGHT = 576    # 16:9
STEPS  = 4
SEED   = 2024   # fixed seed so differences come only from prompt, not randomness

# ── Style variants: all targeting Kurzgesagt/stickman 2D ─────────────────────
# Each variant tests a different keyword emphasis or framing.
# We keep the scene description identical to isolate the prompt effect.

VARIANTS = {
    # V1: Base Kurzgesagt reference, dark background
    "v1_kurzgesagt_dark": (
        "Kurzgesagt YouTube animation style, flat 2D illustration, "
        "dark navy blue background with subtle gradient, bold saturated colors "
        "(orange, teal, yellow, white), thick clean black outlines, "
        "simple geometric stickman characters with round heads, "
        "icons and simple shapes, no photorealism, no 3D, no shading"
    ),
    # V2: Stickman emphasis, white/light background
    "v2_stickman_light": (
        "simple stickman 2D animation illustration, flat colors, "
        "thick black outlines, white or light grey background, "
        "Kurzgesagt-inspired character design with round heads and simple bodies, "
        "bold accent colors, clean vector art style, educational YouTube animation, "
        "no textures, no gradients, no photorealism"
    ),
    # V3: Dark mood Kurzgesagt (true crime adaptation)
    "v3_kurzgesagt_horror": (
        "Kurzgesagt animation style adapted for horror documentary, "
        "very dark background (near black), cold blue and purple accent colors, "
        "ominous red highlights, simple stickman characters with round heads, "
        "flat 2D illustration, thick clean outlines, dramatic but minimal design, "
        "no photorealism, vector art style, no 3D"
    ),
    # V4: Motion graphic / explainer video style
    "v4_motion_graphic": (
        "flat 2D motion graphic explainer video style, "
        "bold primary and secondary colors, thick black outlines, "
        "simple geometric shapes and stick figures, "
        "dark background with bright colored elements, "
        "clean minimal design, YouTube educational animation aesthetic, "
        "Kurzgesagt-like composition, no photorealism, no shadows or shading"
    ),
    # V5: Strong stickman + scene detail
    "v5_stickman_detailed": (
        "2D flat animation, stickman characters with circular heads and thin limbs, "
        "detailed background environment in flat color blocks, "
        "thick consistent black outlines on all elements, "
        "muted dark background tones with bright character colors, "
        "cinematic wide composition, Kurzgesagt quality illustration, "
        "no gradients, no 3D rendering, no photorealism"
    ),
    # V6: Minimal lines, maximum clarity
    "v6_minimal_clear": (
        "ultra clean 2D animation frame, Kurzgesagt infographic style, "
        "black background, simple stick figures and geometric shapes in bold colors, "
        "every element outlined in thick black, flat fill only no gradients, "
        "high contrast, easy to read at small sizes, "
        "YouTube thumbnail-quality composition, no photorealism, no 3D, no textures"
    ),
}

# ── Complex scenes (true crime / horror appropriate) ──────────────────────────
SCENES = {
    # Scene A: Interrogation: small room, 2 characters, tension
    "interrogation": (
        "a detective stickman character sits across a metal table from a nervous suspect "
        "stickman in a small bare room, single overhead lamp casting light, "
        "one-way mirror on the wall, handcuffs on the table, "
        "claustrophobic atmosphere, wide angle shot showing whole room"
    ),
    # Scene B: Street crowd: many characters, city night, police
    "crime_scene_crowd": (
        "a city street at night with dozens of small stickman figures gathered behind "
        "yellow police tape, two detective stickmen examining something on the ground, "
        "police car with flashing lights in background, tall dark buildings, "
        "foggy atmosphere, crowd looking on, wide establishing shot"
    ),
    # Scene C: Courtroom: complex multi-character scene
    "courtroom": (
        "a courtroom scene from the front, stickman judge elevated at the bench, "
        "stickman defendant and lawyers at tables, rows of stickman audience behind, "
        "large windows on the side, serious formal atmosphere, "
        "wide shot showing the full room and all participants"
    ),
}


# ── ComfyUI helpers ────────────────────────────────────────────────────────────

def build_workflow(prompt_text: str, filename_prefix: str) -> dict:
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
        "9": {"class_type": "SaveImage",  "inputs": {"images": ["8", 0], "filename_prefix": filename_prefix}},
    }


def check_comfy() -> bool:
    try:
        urllib.request.urlopen(f"{COMFY_URL}/system_stats", timeout=3)
        return True
    except Exception:
        return False


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
                node    = next(iter(outputs))
                return outputs[node]["images"][0]["filename"]
        except Exception:
            pass
    raise TimeoutError(f"timed out after {timeout}s")


def free_vram() -> None:
    """Tell ComfyUI to release cached models/tensors between generations."""
    try:
        body = json.dumps({"unload_models": True, "free_memory": True}).encode("utf-8")
        req  = urllib.request.Request(f"{COMFY_URL}/free", data=body,
                                       headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
        time.sleep(1)  # give GPU a moment to actually free
    except Exception:
        pass  # non-fatal: generation still works, just higher OOM risk


def generate(variant_key: str, scene_key: str, idx: int, total: int) -> str:
    prompt = f"{VARIANTS[variant_key]}, {SCENES[scene_key]}, no text, no watermarks, no logos"
    prefix = f"v2_{variant_key}_{scene_key}"

    print(f"  [{idx:02d}/{total}] {variant_key} x {scene_key}")
    print(f"         {prompt[:100]}...")

    free_vram()  # clear VRAM before each generation to avoid fragmentation OOM
    pid      = submit(build_workflow(prompt, prefix))
    filename = wait(pid)
    print(f"         -> {filename}\n")
    return filename


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not check_comfy():
        print("ERROR: ComfyUI not running at http://localhost:8188")
        print("\nStart it with:")
        print("  $env:PYTHONIOENCODING='utf-8'")
        print("  $env:PYTHONUTF8='1'")
        print("  cd C:\\dev\\ComfyUI")
        print("  python main.py --port 8188 --highvram")
        sys.exit(1)

    total = len(VARIANTS) * len(SCENES)
    print(f"ComfyUI OK: generating {len(VARIANTS)} variants × {len(SCENES)} scenes = {total} images")
    print(f"Resolution: {WIDTH}x{HEIGHT} | Steps: {STEPS} | Seed: {SEED} (fixed)")
    print(f"All images use the SAME seed, differences = prompt only\n")

    results = []
    idx = 1
    for variant_key in VARIANTS:
        for scene_key in SCENES:
            try:
                fname = generate(variant_key, scene_key, idx, total)
                results.append((variant_key, scene_key, fname, True))
            except Exception as e:
                print(f"         ERROR: {e}\n")
                results.append((variant_key, scene_key, None, False))
            idx += 1

    ok = sum(1 for r in results if r[3])
    print("-- Summary " + "-" * 60)
    print(f"Output: C:\\dev\\ComfyUI\\output\\  (look for v2_v*_*.png)")
    print(f"\n{ok}/{total} OK\n")
    print("Variants generated:")
    for v in VARIANTS:
        files = [r[2] for r in results if r[0] == v and r[3]]
        status = f"OK ({len(files)}/3)" if files else "FAILED"
        print(f"  {v:<35} {status}")
    print()
    print("Once you review the images, tell me which variant code (v1, v6) looks best")
    print("and I'll lock it into config.py as the permanent IMAGE_STYLE_ANCHOR.")


if __name__ == "__main__":
    main()
