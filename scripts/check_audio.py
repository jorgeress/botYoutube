"""
Non-blocking audio/subtitle validation.

Checks:
  - Loudness LUFS of narration_processed.mp3 (should be -15 to -13)
  - Duration match: narration.mp3 vs final_video.mp4 (±0.5s)
  - Existence of subtitles.srt and subtitles.ass
  - Word count in .ass vs segments.json (detects missed beats)
  - Reminder if BACKGROUND_MUSIC_PATH is empty
  - Warning if CHATTERBOX_REF_AUDIO is empty (default voice)

Usage:
    python scripts/check_audio.py [slug]
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    OUTPUT_DIR, CHATTERBOX_REF_AUDIO, BACKGROUND_MUSIC_PATH,
)


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def _duration(path: str) -> float | None:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True,
        )
        return float(r.stdout.strip()) if r.returncode == 0 else None
    except Exception:
        return None


def _measure_lufs(path: str) -> float | None:
    """Run ebur128 scan and return integrated loudness (I) in LUFS.
    Reads the final summary block, not the per-frame lines."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-nostats", "-i", path,
             "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        # The summary appears after "Integrated loudness:" near the end of stderr.
        # Format:  "    I:         -14.3 LUFS"
        # Find the last occurrence (per-frame lines also contain "I:" take the summary).
        matches = re.findall(r"^\s+I:\s+([-\d.]+)\s+LUFS\s*$", r.stderr, re.MULTILINE)
        return float(matches[-1]) if matches else None
    except Exception:
        return None


def _count_ass_words(ass_path: str) -> int:
    """Count words in ASS dialogue lines (strip tags)."""
    total = 0
    with open(ass_path, encoding="utf-8") as f:
        for line in f:
            if not line.startswith("Dialogue:"):
                continue
            # text is after the 9th comma
            parts = line.split(",", 9)
            if len(parts) < 10:
                continue
            text = parts[9]
            # strip ASS override tags {…}
            text = re.sub(r"\{[^}]*\}", "", text)
            total += len(text.split())
    return total


def _count_script_words(seg_path: str) -> int:
    with open(seg_path, encoding="utf-8") as f:
        data = json.load(f)
    return sum(len(b.get("narration", "").split()) for b in data["beats"])


def main():
    slug_arg = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    slug     = find_slug(slug_arg)
    out_dir  = os.path.join(OUTPUT_DIR, slug)

    issues   = []
    warnings = []
    ok       = []

    # ── Config reminders ──────────────────────────────────────────────────────
    if not CHATTERBOX_REF_AUDIO:
        warnings.append("CHATTERBOX_REF_AUDIO is empty, using default Chatterbox voice (non-unique)")
    else:
        ok.append(f"Voice ref: {CHATTERBOX_REF_AUDIO}")

    if not BACKGROUND_MUSIC_PATH:
        warnings.append("BACKGROUND_MUSIC_PATH is empty, no background music will be mixed")
    else:
        ok.append(f"Music: {BACKGROUND_MUSIC_PATH}")

    # ── LUFS check ────────────────────────────────────────────────────────────
    processed = os.path.join(out_dir, "narration_processed.mp3")
    if os.path.exists(processed):
        lufs = _measure_lufs(processed)
        if lufs is None:
            warnings.append("Could not measure LUFS from narration_processed.mp3")
        elif -16.0 <= lufs <= -12.0:
            ok.append(f"LUFS: {lufs:.1f} (target -14, acceptable -16 to -12) OK")
        else:
            issues.append(f"LUFS: {lufs:.1f}: outside acceptable range -16 to -12 LUFS")
    else:
        warnings.append("narration_processed.mp3 not found, AUDIO_POSTPROCESS may be False")

    # ── Duration match ────────────────────────────────────────────────────────
    narration = os.path.join(out_dir, "narration.mp3")
    final     = os.path.join(out_dir, "final_video.mp4")
    dur_nar   = _duration(narration)
    dur_vid   = _duration(final)
    if dur_nar is not None and dur_vid is not None:
        delta = abs(dur_vid - dur_nar)
        if delta <= 0.5:
            ok.append(f"Duration match: narration {dur_nar:.1f}s / video {dur_vid:.1f}s (Δ{delta:.2f}s) OK")
        else:
            issues.append(f"Duration mismatch: narration {dur_nar:.1f}s vs video {dur_vid:.1f}s (Δ{delta:.2f}s)")
    else:
        if dur_nar is None:
            warnings.append("narration.mp3 not found")
        if dur_vid is None:
            warnings.append("final_video.mp4 not found")

    # ── Subtitle files ────────────────────────────────────────────────────────
    srt_path = os.path.join(out_dir, "subtitles.srt")
    ass_path = os.path.join(out_dir, "subtitles.ass")

    if os.path.exists(srt_path):
        ok.append(f"subtitles.srt present")
    else:
        issues.append("subtitles.srt missing, run generate_subtitles.py")

    if os.path.exists(ass_path):
        ok.append(f"subtitles.ass present")
    else:
        issues.append("subtitles.ass missing, run generate_subtitles.py")

    # ── Word count match ──────────────────────────────────────────────────────
    seg_path = os.path.join(out_dir, "segments.json")
    if os.path.exists(ass_path) and os.path.exists(seg_path):
        ass_words    = _count_ass_words(ass_path)
        script_words = _count_script_words(seg_path)
        ratio        = ass_words / script_words if script_words > 0 else 0
        if ratio >= 0.95:
            ok.append(f"Word count: ASS {ass_words} / script {script_words} ({ratio:.0%}) OK")
        else:
            issues.append(
                f"Word count mismatch: ASS has {ass_words} words, script has {script_words} "
                f"({ratio:.0%}): some beats may not have been aligned"
            )

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\nAudio check: {slug}")
    for msg in ok:
        print(f"  OK  {msg}")
    for msg in warnings:
        print(f"  WARN  {msg}")
    for msg in issues:
        print(f"  FAIL  {msg}")

    if not issues and not warnings:
        print("\nAll checks passed.")
    elif not issues:
        print(f"\n{len(warnings)} reminder(s). No blocking issues.")
    else:
        print(f"\n{len(issues)} issue(s), {len(warnings)} warning(s).")

    return len(issues)


if __name__ == "__main__":
    sys.exit(main())
