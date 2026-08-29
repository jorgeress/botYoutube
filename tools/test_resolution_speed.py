"""
Resolution/speed sweet spot test: uses the locked v5 style.
Tests 4 resolutions with timing to find best quality/speed tradeoff.

Each resolution generates the same scene twice (seed variation) to check consistency.
Total: 4 resolutions x 2 seeds = 8 images.

Output: C:\\dev\\ComfyUI\\output\\res_<WxH>_s<seed>_*.png
"""

import json
import sys
import time
import urllib.request

COMFY_URL = "http://localhost:8188"
STEPS = 4

# v5 style + face details (locked)
STYLE = (
    "2D flat animation, stickman characters with circular heads and thin limbs, "
    "characters have visible dot eyes and small curved mouth line for expression, "
    "detailed background environment in flat color blocks, "
    "thick consistent black outlines on all elements, "
    "muted dark background tones with bright character colors, "
    "Kurzgesagt quality illustration, no gradients, no 3D rendering, no photorealism"
)

# Fixed complex scene (multi-character, background detail)
SCENE = (
    "a courtroom scene, stickman judge elevated at the bench, "
    "stickman defendant and lawyers at tables, rows of stickman audience behind, "
    "large windows on the side, serious formal atmosphere, wide shot showing full room"
)

# Resolutions to test: all 16:9
RESOLUTIONS = [
    (512,  288,  "512x288  (fast)"),
    (640,  360,  "640x360  (medium-fast)"),
    (768,  432,  "768x432  (medium - likely sweet spot)"),
    (1024, 576,  "1024x576 (current default)"),
]

SEEDS = [2024, 9999]


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


def get_vram_free() -> str:
    try:
        data = json.loads(urllib.request.urlopen(
            f"{COMFY_URL}/system_stats", timeout=5).read())
        free = data["devices"][0]["vram_free"]
        return f"{free / 1024**3:.1f}GB"
    except Exception:
        return "?"


def build_workflow(prompt_text: str, prefix: str, seed: int, w: int, h: int) -> dict:
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
        "6": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "positive": ["4", 0], "negative": ["5", 0],
            "latent_image": ["6", 0], "seed": seed, "steps": STEPS,
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
        time.sleep(2)
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


def main():
    if not check_comfy():
        print("ERROR: ComfyUI not running at http://localhost:8188")
        sys.exit(1)

    total = len(RESOLUTIONS) * len(SEEDS)
    print(f"Resolution sweet-spot test: {len(RESOLUTIONS)} resolutions x {len(SEEDS)} seeds = {total} images")
    print(f"Style: v5_stickman_detailed + face expressions\n")

    prompt = f"{STYLE}, {SCENE}, no text, no watermarks, no logos"
    results = []
    idx = 1

    for (w, h, label) in RESOLUTIONS:
        for seed in SEEDS:
            prefix = f"res_{w}x{h}_s{seed}"
            print(f"  [{idx:02d}/{total}] {label}  seed={seed}  VRAM free: {get_vram_free()}")

            free_vram()
            t0 = time.time()
            try:
                pid      = submit(build_workflow(prompt, prefix, seed, w, h))
                filename = wait(pid)
                elapsed  = time.time() - t0
                print(f"         -> {filename}  ({elapsed:.1f}s)\n")
                results.append((label, seed, filename, elapsed, True))
            except Exception as e:
                elapsed = time.time() - t0
                print(f"         ERROR after {elapsed:.1f}s: {e}\n")
                results.append((label, seed, None, elapsed, False))
            idx += 1

    print("-- Results " + "-" * 55)
    print(f"{'Resolution':<28} {'Seed':<6} {'Time':>6}  {'File'}")
    print("-" * 75)
    for (label, seed, fname, t, ok) in results:
        status = fname if ok else "FAILED"
        print(f"  {label:<26} {seed:<6} {t:>5.1f}s  {status}")

    print("\nFiles in C:\\dev\\ComfyUI\\output\\  (look for res_*.png)")
    print("Pick the lowest resolution that still looks sharp enough for your use case.")


if __name__ == "__main__":
    main()
