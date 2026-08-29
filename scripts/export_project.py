"""
Creates IMPORT_GUIDE.txt in the output/<slug>/ folder with CapCut assembly
instructions and an ordered checklist.

Usage:
    python scripts/export_project.py [slug]
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders found in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def main():
    slug_arg = sys.argv[1] if len(sys.argv) > 1 else None
    slug = find_slug(slug_arg)
    out_dir = os.path.join(OUTPUT_DIR, slug)
    segments_path = os.path.join(out_dir, "segments.json")

    if not os.path.exists(segments_path):
        print(f"ERROR: {segments_path} not found. Run parse_script.py first.")
        sys.exit(1)

    with open(segments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]
    title = data["title"]

    lines = [
        f"IMPORT GUIDE: {title}",
        "=" * 60,
        "",
        "STEP 1: Generate narration audio",
        "  Run: python scripts/generate_voice.py",
        f"  Output: output/{slug}/narration.mp3",
        "",
        "STEP 2: Get subtitles (manual)",
        f"  1. Upload output/{slug}/narration.mp3 to https://turboscribe.ai",
        "  2. Download the .srt file",
        f"  3. Save it as: output/{slug}/subtitles.srt",
        "",
        "STEP 3: Generate video clips",
        "  Run: python scripts/generate_clips.py",
        "  (Follow the printed /higgsfield:generate instructions per segment)",
        "",
        "STEP 4: CapCut assembly",
        "",
        "  Import the following clips INTO THE TIMELINE IN THIS ORDER:",
        "",
    ]

    for seg in segments:
        idx = str(seg["id"]).zfill(2)
        lines.append(f"  [{idx}] clips/seg_{idx}.mp4")
        lines.append(f"       Narration: {seg['narration_text'][:80]}...")
        lines.append("")

    lines += [
        "  Import narration.mp3 as the audio track.",
        "  Import subtitles.srt for auto-captions.",
        "  Add background music from CapCut free library (low volume, ~15%).",
        "",
        "CAPCUT ASSEMBLY CHECKLIST",
        "  [ ] All clips imported in order",
        "  [ ] narration.mp3 audio track added",
        "  [ ] subtitles.srt imported",
        "  [ ] Background music added",
        "  [ ] Video exported at 1080p or 4K",
        "  [ ] Thumbnail created",
        "  [ ] YouTube title, description, tags written",
        "",
        "=" * 60,
        f"Output folder: output/{slug}/",
    ]

    guide_path = os.path.join(out_dir, "IMPORT_GUIDE.txt")
    with open(guide_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"IMPORT_GUIDE.txt written to: {guide_path}")


if __name__ == "__main__":
    main()
