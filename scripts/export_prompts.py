"""
Export image prompts to a copy-paste friendly file for MANUAL generation in the
AI Studio web UI (the free Nano Banana tier), then save each result as
clips/seg_NNN_src.png so the pipeline can build the video from them.

Usage:
    python scripts/export_prompts.py [slug]

Output: output/<slug>/prompts_for_manual.txt
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR, CHARACTER_REFERENCE_IMAGE


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def main():
    slug_arg = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    slug     = find_slug(slug_arg)
    out_dir  = os.path.join(OUTPUT_DIR, slug)
    prompts_path = os.path.join(out_dir, "image_prompts.json")
    if not os.path.exists(prompts_path):
        print(f"ERROR: {prompts_path} not found. Run generate_image_prompts.py first.")
        sys.exit(1)

    with open(prompts_path, encoding="utf-8") as f:
        entries = json.load(f)

    clips_dir = os.path.abspath(os.path.join(out_dir, "clips"))
    os.makedirs(clips_dir, exist_ok=True)
    ref = os.path.abspath(CHARACTER_REFERENCE_IMAGE) if CHARACTER_REFERENCE_IMAGE else ""

    total = len(entries)
    lines: list[str] = []
    lines.append(f"MANUAL IMAGE GENERATION  -  {slug}")
    lines.append("=" * 70)
    lines.append(f"{total} images to generate in AI Studio (https://aistudio.google.com).")
    lines.append("")
    lines.append("For EACH block below:")
    lines.append("  1. Model: Nano Banana (Gemini 2.5 Flash Image). Aspect ratio: 16:9.")
    if ref:
        lines.append(f"  2. Attach this reference image for a consistent character: {ref}")
    else:
        lines.append("  2. (Optional) Attach a character model-sheet image for consistency.")
    lines.append("  3. Paste the PROMPT, generate, download the image.")
    lines.append(f"  4. Save it with the exact FILENAME shown, into:")
    lines.append(f"       {clips_dir}")
    lines.append("")
    lines.append("Then run:  python run_pipeline.py " + slug)
    lines.append("It is re-runnable: it builds clips only for images already saved, so you")
    lines.append("can do them in batches and re-run as you go.")
    lines.append("=" * 70)
    lines.append("")

    for i, e in enumerate(entries, 1):
        idx = str(e["index"]).zfill(3)
        prompt = (e.get("image_prompt") or "").strip()
        narr   = (e.get("narration") or "").strip()
        lines.append(f"[{i}/{total}]  FILENAME: seg_{idx}_src.png")
        if narr:
            lines.append(f"narration: {narr}")
        lines.append("PROMPT:")
        lines.append(prompt if prompt else "(empty prompt, skip this one)")
        lines.append("-" * 70)

    out_path = os.path.join(out_dir, "prompts_for_manual.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Wrote {total} prompts -> {out_path}")
    print(f"Save your downloaded images into: {clips_dir}")
    print(f"Then: python run_pipeline.py {slug}")


if __name__ == "__main__":
    main()
