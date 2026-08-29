"""
Assembles all Ken Burns clips + narration.mp3 into final_video.mp4 using FFmpeg.

Reads image_prompts.json for clip order and timings.
Optionally burns subtitles.srt into the video (see BURN_SUBTITLES in config.py).

Usage:
    python scripts/assemble_video.py [slug]
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    ASSEMBLE_WITH_FFMPEG, BURN_SUBTITLES, OUTPUT_DIR,
    BACKGROUND_MUSIC_PATH, BACKGROUND_MUSIC_DB,
)


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders found in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def mix_background_music(narration: str, music: str, output: str,
                          music_db: float = -20.0) -> None:
    """Mix narration with looped background music at music_db dB relative volume."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", narration,
            "-stream_loop", "-1", "-i", music,
            "-filter_complex",
            f"[1:a]volume={music_db}dB[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=2[out]",
            "-map", "[out]",
            output,
        ],
        check=True, capture_output=True,
    )


def burn_subtitles(video_in: str, ass_path: str, video_out: str) -> None:
    """Burn .ass subtitles into video using libass. Handles Windows path escaping."""
    # Windows paths: convert backslashes and escape the colon in drive letter (C: → C\:)
    ass_escaped = ass_path.replace("\\", "/")
    # Escape colon in drive letter only (e.g. C:/... → C\:/...)
    if len(ass_escaped) >= 2 and ass_escaped[1] == ":":
        ass_escaped = ass_escaped[0] + "\\:" + ass_escaped[2:]
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_in,
            "-vf", f"ass='{ass_escaped}'",
            "-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20",
            "-c:a", "copy",
            video_out,
        ],
        check=True, capture_output=True,
    )


def check_clips(entries: list[dict], clips_dir: str) -> list[str]:
    missing = []
    for entry in entries:
        idx = str(entry["index"]).zfill(3)
        clip = os.path.join(clips_dir, f"seg_{idx}.mp4")
        if not os.path.exists(clip):
            missing.append(f"seg_{idx}.mp4")
    return missing


def main():
    if not ASSEMBLE_WITH_FFMPEG:
        print("ASSEMBLE_WITH_FFMPEG is False. Skipping assembly, use CapCut manually.")
        return

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
    missing = check_clips(entries, clips_dir)
    if missing:
        print(f"ERROR: {len(missing)} clip(s) missing. Run generate_clips.py first.")
        for m in missing[:5]:
            print(f"  {m}")
        if len(missing) > 5:
            print(f"  ... and {len(missing)-5} more")
        sys.exit(1)

    # Prefer narration_processed.mp3 (post-EQ/loudnorm), fall back to narration.mp3
    narration_processed = os.path.join(out_dir, "narration_processed.mp3")
    narration_raw       = os.path.join(out_dir, "narration.mp3")
    if os.path.exists(narration_processed):
        narration_path = narration_processed
        print("  Using narration_processed.mp3 (post-EQ/loudnorm)")
    elif os.path.exists(narration_raw):
        narration_path = narration_raw
    else:
        print(f"ERROR: narration.mp3 not found in {out_dir}. Run generate_voice.py first.")
        sys.exit(1)

    final_path = os.path.join(out_dir, "final_video.mp4")
    ass_path   = os.path.join(out_dir, "subtitles.ass")

    print(f"Assembling {len(entries)} clips → {final_path}")

    with tempfile.TemporaryDirectory() as tmp:
        # Step 1: concatenate video clips
        concat_path = os.path.join(tmp, "concat.txt")
        with open(concat_path, "w") as f:
            for entry in entries:
                idx = str(entry["index"]).zfill(3)
                clip_abs = os.path.abspath(os.path.join(clips_dir, f"seg_{idx}.mp4"))
                f.write(f"file '{clip_abs}'\n")

        print("  Concatenating clips...")
        video_only = os.path.join(tmp, "video_only.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
             "-i", concat_path, "-c:v", "copy", video_only],
            check=True, capture_output=True,
        )

        # Step 2: mix background music if configured
        if BACKGROUND_MUSIC_PATH and os.path.exists(BACKGROUND_MUSIC_PATH):
            print(f"  Mixing background music ({BACKGROUND_MUSIC_DB} dB)...")
            audio_mixed = os.path.join(tmp, "audio_mixed.mp3")
            mix_background_music(narration_path, BACKGROUND_MUSIC_PATH,
                                 audio_mixed, BACKGROUND_MUSIC_DB)
            audio_path = audio_mixed
        else:
            audio_path = narration_path

        # Step 3: mux video + audio
        print("  Muxing video + audio...")
        muxed = os.path.join(tmp, "muxed.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_only, "-i", audio_path,
             "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", muxed],
            check=True, capture_output=True,
        )

        # Step 4: burn subtitles (last pass, re-encodes video)
        if BURN_SUBTITLES and os.path.exists(ass_path):
            print("  Burning .ass subtitles...")
            burn_subtitles(muxed, os.path.abspath(ass_path), final_path)
        else:
            if BURN_SUBTITLES and not os.path.exists(ass_path):
                print("  WARN: BURN_SUBTITLES=True but subtitles.ass not found, skipping burn")
            import shutil
            shutil.copy2(muxed, final_path)

    size_mb = os.path.getsize(final_path) / (1024 * 1024)
    total_s = entries[-1]["end"] if entries else 0
    print(f"  Done: {final_path} ({size_mb:.1f} MB, ~{total_s/60:.1f} min)")


if __name__ == "__main__":
    main()
