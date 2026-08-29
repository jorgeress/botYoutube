"""
Full pipeline runner:
  parse → voice → image_prompts → clips → subtitles → assemble → check_audio → thumbnails

All steps are idempotent: already-completed work is skipped on re-run.
Flags:
  --force-subtitles   Regenerate subtitles even if they exist
  --thumbnails        Generate thumbnail variants (4 PIL images, no ComfyUI needed)

Usage:
    python run_pipeline.py [slug] [--force-subtitles] [--thumbnails]
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ASSEMBLE_WITH_FFMPEG, OUTPUT_DIR


def run(label: str, cmd: list[str]) -> None:
    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\nERROR: '{label}' failed. Fix the issue and re-run.")
        sys.exit(result.returncode)


def find_slug_from_output() -> str | None:
    if not os.path.isdir(OUTPUT_DIR):
        return None
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        return None
    return max(entries, key=lambda e: e.stat().st_mtime).name


def main():
    args       = sys.argv[1:]
    force_subs = "--force-subtitles" in args
    do_thumbs  = "--thumbnails" in args
    slug_arg   = next((a for a in args if not a.startswith("--")), None)

    # ── Step 1: Parse ──────────────────────────────────────────────────────────
    from scripts.parse_script import main as parse_main

    segments_path = None
    if slug_arg:
        segments_path = os.path.join(OUTPUT_DIR, slug_arg, "segments.json")

    if segments_path and os.path.exists(segments_path):
        slug = slug_arg
        print(f"[parse] segments.json already exists for '{slug}', skipping.")
    else:
        print(f"\n{'='*55}\n  Parsing script\n{'='*55}")
        result = parse_main()
        slug = result["slug"]

    # ── Step 2: Voice + post-processing ───────────────────────────────────────
    narration_path = os.path.join(OUTPUT_DIR, slug, "narration.mp3")
    if os.path.exists(narration_path):
        print(f"\n[voice] narration.mp3 already exists, skipping.")
    else:
        run("Generating voice narration", ["python", "scripts/generate_voice.py", slug])

    # ── Step 3: Generate image prompts (uses actual audio timing) ─────────────
    prompts_path = os.path.join(OUTPUT_DIR, slug, "image_prompts.json")
    if os.path.exists(prompts_path):
        print(f"\n[image_prompts] image_prompts.json already exists, skipping.")
    else:
        run("Generating image prompts", ["python", "scripts/generate_image_prompts.py", slug])

    # ── Step 4: Generate clips (resumes automatically) ────────────────────────
    run("Generating clips", ["python", "scripts/generate_clips.py", slug])

    # ── Step 5: Generate subtitles (forced alignment) ─────────────────────────
    ass_path = os.path.join(OUTPUT_DIR, slug, "subtitles.ass")
    if os.path.exists(ass_path) and not force_subs:
        print(f"\n[subtitles] subtitles.ass already exists, skipping.")
    else:
        sub_cmd = ["python", "scripts/generate_subtitles.py", slug]
        if force_subs:
            sub_cmd.append("--force")
        run("Generating subtitles (forced alignment)", sub_cmd)

    # ── Step 6: Assemble final video ──────────────────────────────────────────
    if ASSEMBLE_WITH_FFMPEG:
        final_path = os.path.join(OUTPUT_DIR, slug, "final_video.mp4")
        if os.path.exists(final_path):
            print(f"\n[assemble] final_video.mp4 already exists, skipping.")
        else:
            run("Assembling final video", ["python", "scripts/assemble_video.py", slug])

    # ── Step 7: Audio validation (non-blocking) ───────────────────────────────
    run("Checking audio & subtitles", ["python", "scripts/check_audio.py", slug])

    # ── Step 8: Thumbnails (optional, --thumbnails flag) ──────────────────────
    if do_thumbs:
        thumb_dir = os.path.join(OUTPUT_DIR, slug, "thumbnails")
        run("Generating thumbnails", ["python", "scripts/generate_thumbnails.py", slug])
    else:
        thumb_dir = os.path.join(OUTPUT_DIR, slug, "thumbnails")
        if not os.path.isdir(thumb_dir):
            print(f"\n[thumbnails] Tip: run with --thumbnails to generate 4 thumbnail variants.")

    print(f"\nPipeline complete. Output: output/{slug}/")


if __name__ == "__main__":
    main()
