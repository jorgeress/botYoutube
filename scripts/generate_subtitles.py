"""
Generates word-level karaoke subtitles for the final video.

Uses stable-ts forced alignment: the narration text per beat is known exactly,
so we skip transcription and go straight to alignment (faster + more accurate).

Outputs:
    output/<slug>/subtitles.srt: clean SRT for YouTube closed captions
    output/<slug>/subtitles.ass: karaoke ASS with active word highlighted yellow

Usage:
    python scripts/generate_subtitles.py [slug] [--force]
"""

import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR, SEGMENT_SILENCE_MS, BEAT_SILENCE_MS, SUBTITLE_STYLE

try:
    import stable_whisper
except ImportError:
    print("ERROR: stable-ts not installed. Run: pip install stable-ts")
    sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mp3_duration(path: str) -> float:
    """Return actual duration of an mp3 via ffprobe (same method as image_prompts.py)."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip()) if r.returncode == 0 else 3.0


def _load_beat_timings(out_dir: str) -> dict[int, dict] | None:
    """Authoritative per-beat timeline from generate_voice.py, or None (legacy)."""
    path = os.path.join(out_dir, "beat_timings.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {b["index"]: b for b in data.get("beats", [])}
    except Exception:
        return None

_PUNCT_ONLY = frozenset({': ', ', ', '--', '-', '.', ',', '...', '…'})


def _is_punct_token(word: str) -> bool:
    """Return True if the word is a pure punctuation token that should be skipped in subtitles."""
    return word.strip() in _PUNCT_ONLY or word.strip(',  -. ') == ''


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - math.floor(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _build_ass_header(style: dict) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "Timer: 100.0000\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{style['font']},{style['font_size']},"
        f"{style['color_base']},{style['color_active']},"
        f"{style['outline_color']},&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,{style['outline_width']},1,2,20,20,30,1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


# ── Forced alignment ──────────────────────────────────────────────────────────

def align_beat(model, audio_path: str, text: str) -> list[dict]:
    """
    Return list of {word, start, end} with times relative to the audio file.
    Uses stable-ts forced alignment: text is known so no transcription needed.
    """
    result = model.align(audio_path, text, language="en")
    words = []
    for seg in result.segments:
        for w in seg.words:
            word_text = getattr(w, "word", "").strip()
            if word_text:
                words.append({
                    "word":  word_text,
                    "start": round(w.start, 3),
                    "end":   round(w.end, 3),
                })
    return words


# ── SRT generation ────────────────────────────────────────────────────────────

def _build_srt(all_words: list[dict], max_words: int) -> str:
    lines = []
    idx = 1
    i = 0
    while i < len(all_words):
        chunk: list[dict] = []
        while i < len(all_words) and len(chunk) < max_words:
            w = all_words[i]
            i += 1
            if w.get("_force_break"):
                break  # flush at beat boundary even if chunk is smaller than max_words
            if _is_punct_token(w.get("word", "")):
                continue  # skip pure punctuation tokens (em-dash etc.)
            chunk.append(w)
        if not chunk:
            continue
        t_start = chunk[0]["start"]
        t_end   = chunk[-1]["end"]
        text    = " ".join(w["word"] for w in chunk)
        lines.append(
            f"{idx}\n"
            f"{_format_srt_time(t_start)} --> {_format_srt_time(t_end)}\n"
            f"{text}\n"
        )
        idx += 1
    return "\n".join(lines)


# ── ASS karaoke generation ────────────────────────────────────────────────────

def _build_ass(all_words: list[dict], style: dict) -> str:
    """
    Build .ass karaoke content. Words are grouped in chunks of max_words.
    Each word gets a {\\k<cs>} tag (centiseconds). The active word is colored
    via {\\1c<color_active>} at fire time using {\\kf} karaoke fill timing.
    """
    max_words   = style["max_words"]
    color_base  = style["color_base"]
    color_active = style["color_active"]
    pos_y       = style["position_y"]

    header  = _build_ass_header(style)
    events  = []

    i = 0
    while i < len(all_words):
        chunk: list[dict] = []
        while i < len(all_words) and len(chunk) < max_words:
            w = all_words[i]
            i += 1
            if w.get("_force_break"):
                break  # flush at beat boundary
            if _is_punct_token(w.get("word", "")):
                continue  # skip pure punctuation tokens (em-dash etc.)
            chunk.append(w)
        if not chunk:
            continue

        t_start = chunk[0]["start"]
        t_end   = chunk[-1]["end"]

        # Build karaoke text: each word preceded by {\kf<cs>}
        # {\kf} = fill-karaoke: sweeps color from left to right over the duration
        parts = []
        for w in chunk:
            dur_cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            parts.append(f"{{\\kf{dur_cs}}}{w['word']}")

        # Wrap in position override and base color reset
        text = f"{{\\an2\\pos(960,{pos_y})\\1c{color_base}}}" + " ".join(parts)

        events.append(
            f"Dialogue: 0,{_format_ass_time(t_start)},{_format_ass_time(t_end)},"
            f"Default,,0,0,0,,{text}"
        )

    return header + "\n".join(events) + "\n"


# ── Main ──────────────────────────────────────────────────────────────────────

def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def main():
    args     = sys.argv[1:]
    force    = "--force" in args
    slug_arg = next((a for a in args if not a.startswith("--")), None)
    slug     = find_slug(slug_arg)
    out_dir  = os.path.join(OUTPUT_DIR, slug)

    srt_path = os.path.join(out_dir, "subtitles.srt")
    ass_path = os.path.join(out_dir, "subtitles.ass")

    if os.path.exists(ass_path) and not force:
        print(f"subtitles.ass already exists. Use --force to regenerate.")
        return

    seg_path = os.path.join(out_dir, "segments.json")
    if not os.path.exists(seg_path):
        print(f"ERROR: {seg_path} not found. Run parse_script.py first.")
        sys.exit(1)

    with open(seg_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = data["beats"]

    seg_dir = os.path.join(out_dir, "narration_segments")
    timings = _load_beat_timings(out_dir)  # authoritative timeline, or None (legacy)

    print(f"Aligning {len(beats)} beats for: {slug}")
    if timings:
        print("  Using beat_timings.json (gapless audio timeline).")
    print("Loading Whisper base model for forced alignment...")
    model = stable_whisper.load_model("base")
    print("  Model ready.\n")

    all_words: list[dict] = []
    cursor = 0.0

    for i, beat in enumerate(beats):
        idx      = beat["index"]
        mp3_path = os.path.join(seg_dir, f"beat_{idx:03d}.mp3")
        t        = timings.get(idx) if timings else None

        if not os.path.exists(mp3_path):
            print(f"  WARN: {mp3_path} missing, skipping beat {idx}")
            # Keep the timeline consistent: jump to the next beat's known start.
            cursor = (t["start"] + t["duration"] + t["gap_after"]) if t else cursor + 3.0
            continue

        narration = beat.get("narration", "").strip()
        if not narration:
            continue

        # Anchor each beat at its authoritative start (gapless audio); fall back to
        # the running cursor when there is no beat_timings.json.
        beat_start = t["start"] if t else cursor
        words = align_beat(model, mp3_path, narration)

        # Shift word times to absolute video position
        for w in words:
            w["start"] = round(w["start"] + beat_start, 3)
            w["end"]   = round(w["end"]   + beat_start, 3)
        all_words.extend(words)

        # Advance cursor to the next beat's start. With timings this is exact;
        # otherwise reconstruct from the mp3 duration + the configured gap.
        if t is not None:
            cursor = round(t["start"] + t["duration"] + t["gap_after"], 3)
        else:
            beat_dur = _mp3_duration(mp3_path)
            if i < len(beats) - 1:
                same_seg = beats[i]["segment_id"] == beats[i + 1]["segment_id"]
                gap_s    = (BEAT_SILENCE_MS if same_seg else SEGMENT_SILENCE_MS) / 1000.0
            else:
                gap_s = 0.0
            cursor = round(beat_start + beat_dur + gap_s, 3)

        # Force a subtitle chunk break at every beat boundary so no group
        # ever straddles two different beats.
        all_words.append({"word": None, "start": cursor, "end": cursor, "_force_break": True})

        print(f"  beat_{idx:03d}: {len(words)} words aligned (offset {beat_start:.2f}s)")

    if not all_words:
        print("ERROR: no words aligned. Check narration_segments/ for beat MP3s.")
        sys.exit(1)

    # Write SRT
    srt_content = _build_srt(all_words, SUBTITLE_STYLE["max_words"])
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
    print(f"\nSRT: {srt_path}")

    # Write ASS karaoke
    ass_content = _build_ass(all_words, SUBTITLE_STYLE)
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
    print(f"ASS: {ass_path}")
    print(f"\n{len(all_words)} words aligned across {len(beats)} beats.")


if __name__ == "__main__":
    main()
