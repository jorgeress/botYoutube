"""
Generates per-segment narration using Chatterbox TTS (local GPU), then merges
into a single narration.mp3 with short silences between segments via ffmpeg.

Install:
    pip install chatterbox-tts torchaudio

Voice cloning (optional):
    Set CHATTERBOX_REF_AUDIO in config.py to the path of a .wav reference clip
    (10-30s of clean speech from the target voice). Leave empty for default voice.

Usage:
    python scripts/generate_voice.py [slug]
    If slug is omitted, uses the most recently modified output/<slug>/ folder.
"""

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    OUTPUT_DIR,
    SEGMENT_SILENCE_MS,
    BEAT_SILENCE_MS,
    CHATTERBOX_REF_AUDIO,
    CHATTERBOX_EXAGGERATION,
    CHATTERBOX_CFG,
    TTS_SPEED,
    AUDIO_POSTPROCESS,
)

try:
    import torch
    import torchaudio as ta
    from chatterbox.tts import ChatterboxTTS
except ImportError:
    print("ERROR: Chatterbox not installed.")
    print("  pip install chatterbox-tts torchaudio")
    sys.exit(1)


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders found in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def load_model() -> ChatterboxTTS:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Chatterbox on {device.upper()}...")
    model = ChatterboxTTS.from_pretrained(device=device)
    print("  Model ready.\n")
    return model


def generate_segment(model: ChatterboxTTS, text: str, wav_path: str) -> None:
    ref = CHATTERBOX_REF_AUDIO.strip() if CHATTERBOX_REF_AUDIO else None
    if ref and not os.path.exists(ref):
        print(f"  WARNING: ref audio not found at {ref}, using default voice")
        ref = None

    kwargs = {
        "exaggeration": CHATTERBOX_EXAGGERATION,
        "cfg_weight": CHATTERBOX_CFG,
    }
    if ref:
        kwargs["audio_prompt_path"] = ref

    wav = model.generate(text, **kwargs)
    ta.save(wav_path, wav, model.sr)


def wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path,
         "-codec:a", "libmp3lame", "-qscale:a", "2",
         mp3_path],
        check=True, capture_output=True,
    )


def apply_speed(mp3_path: str, speed: float) -> None:
    if speed == 1.0:
        return
    tmp = mp3_path + ".speed_tmp.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp3_path,
         "-filter:a", f"atempo={speed}",
         "-codec:a", "libmp3lame", "-qscale:a", "2",
         tmp],
        check=True, capture_output=True,
    )
    os.replace(tmp, mp3_path)


def _sanitize_for_tts(text: str) -> str:
    """Replace em-dashes and double-dashes with a comma so TTS produces a natural pause."""
    import re
    text = text.replace(': ', ',').replace('--', ',').replace(', ', ',')
    text = re.sub(r',\s*,', ',', text)  # collapse accidental double commas
    return text.strip()


def measure_mp3_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip()) if result.returncode == 0 else 0.0


def measure_decoded_duration(path: str) -> float:
    """
    Exact duration of an mp3 AS DECODED to PCM (encoder delay/padding trimmed).

    ffprobe on the mp3 reports the *coded* duration, which is ~50ms longer per file
    than the decoded audio. The gapless merge concatenates decoded PCM, so beat
    timings must use this decoded measurement or they drift (~4-5s over ~80 beats).
    """
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "d.wav")
        subprocess.run(["ffmpeg", "-y", "-i", path, wav],
                       check=True, capture_output=True)
        return measure_mp3_duration(wav)


def merge_beats(beat_paths: list[str], gap_ms: list[int], out_path: str) -> list[float]:
    """
    Concatenate beat mp3s GAPLESSLY into one narration.mp3.

    Each beat gets `gap_ms[i]` of trailing silence via `apad`, then all beats are
    joined with the `concat` filter (decode → PCM → concatenate → single encode).
    This avoids the per-file mp3 encoder-delay padding that `-c copy` concat leaves
    between segments: that padding accumulates to several seconds over ~80 beats and
    desyncs images/subtitles from the audio.

    Returns the decoded duration (seconds) of each beat, in order, the authoritative
    timeline the image and subtitle steps reuse via beat_timings.json.
    """
    inputs: list[str] = []
    for p in beat_paths:
        inputs += ["-i", os.path.abspath(p)]

    filter_parts: list[str] = []
    labels: list[str] = []
    for i in range(len(beat_paths)):
        gap_s = (gap_ms[i] / 1000.0) if i < len(gap_ms) else 0.0
        # apad pad_dur=0 is a harmless no-op, so every beat goes through the same path.
        filter_parts.append(f"[{i}:a]apad=pad_dur={gap_s:.3f}[a{i}]")
        labels.append(f"[a{i}]")
    filtergraph = (";".join(filter_parts) + ";"
                   + "".join(labels) + f"concat=n={len(beat_paths)}:v=0:a=1[out]")

    subprocess.run(
        ["ffmpeg", "-y", *inputs,
         "-filter_complex", filtergraph, "-map", "[out]",
         "-c:a", "libmp3lame", "-q:a", "2", out_path],
        check=True, capture_output=True,
    )

    # Decoded (not coded) durations: these match the gapless PCM the filter placed.
    durations = [measure_decoded_duration(p) for p in beat_paths]
    total = measure_mp3_duration(out_path)
    print(f"  Merged narration (gapless): {out_path} ({total:.1f}s)")
    return durations


_AUDIO_FILTER = (
    "highpass=f=80,"
    "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,"
    "equalizer=f=2500:width_type=o:width=2:g=2,"
    "loudnorm=I=-14:TP=-1.5:LRA=11"
)


def postprocess_audio(input_path: str, output_path: str) -> None:
    """Apply EQ, compression, and LUFS normalization to the merged narration."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-af", _AUDIO_FILTER, output_path],
        check=True, capture_output=True,
    )


def main():
    slug_arg = sys.argv[1] if len(sys.argv) > 1 else None
    slug     = find_slug(slug_arg)
    out_dir  = os.path.join(OUTPUT_DIR, slug)
    segments_path = os.path.join(out_dir, "segments.json")

    if not os.path.exists(segments_path):
        print(f"ERROR: {segments_path} not found. Run parse_script.py first.")
        sys.exit(1)

    with open(segments_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    beats    = data["beats"]
    seg_dir  = os.path.join(out_dir, "narration_segments")
    os.makedirs(seg_dir, exist_ok=True)
    narration_out = os.path.join(out_dir, "narration.mp3")

    print(f"Voice: {data['title']} ({len(beats)} beats)")
    ref_label = CHATTERBOX_REF_AUDIO or "default voice"
    print(f"  voice ref: {ref_label}\n")

    model = load_model()

    beat_mp3_paths = []
    for beat in beats:
        idx      = str(beat["index"]).zfill(3)
        wav_path = os.path.join(seg_dir, f"beat_{idx}.wav")
        mp3_path = os.path.join(seg_dir, f"beat_{idx}.mp3")

        if os.path.exists(mp3_path):
            print(f"  beat_{idx}.mp3 already exists, skipping")
        else:
            tts_text = _sanitize_for_tts(beat["narration"])
            print(f"  Generating beat_{idx}: {tts_text[:60]}...")
            generate_segment(model, tts_text, wav_path)
            wav_to_mp3(wav_path, mp3_path)
            os.remove(wav_path)
            if TTS_SPEED != 1.0:
                apply_speed(mp3_path, TTS_SPEED)
            print(f"  Saved beat_{idx}.mp3")

        beat_mp3_paths.append(mp3_path)

    # Gap after each beat: bigger pause when the next beat starts a new segment
    gaps = []
    for i in range(len(beats) - 1):
        same_segment = beats[i]["segment_id"] == beats[i + 1]["segment_id"]
        gaps.append(BEAT_SILENCE_MS if same_segment else SEGMENT_SILENCE_MS)
    gaps.append(0)  # no gap after the final beat

    print("\nMerging beats...")
    durations = merge_beats(beat_mp3_paths, gaps, narration_out)

    # Authoritative timeline: write per-beat start/duration/gap so the image and
    # subtitle steps share the EXACT offsets used to build the gapless audio.
    timings = []
    cursor = 0.0
    for i, beat in enumerate(beats):
        dur     = durations[i]
        gap_s   = gaps[i] / 1000.0
        timings.append({
            "index":     beat["index"],
            "start":     round(cursor, 3),
            "duration":  round(dur, 3),
            "gap_after": round(gap_s, 3),
        })
        cursor += dur + gap_s
    timings_path = os.path.join(out_dir, "beat_timings.json")
    with open(timings_path, "w", encoding="utf-8") as f:
        json.dump({"beats": timings, "total": round(cursor, 3)}, f, indent=2)
    print(f"  Wrote timeline: {timings_path}")

    if AUDIO_POSTPROCESS:
        processed_out = os.path.join(out_dir, "narration_processed.mp3")
        print("Post-processing audio (EQ + loudnorm -14 LUFS)...")
        postprocess_audio(narration_out, processed_out)
        print(f"  Saved: {processed_out}")

    print("Done.")


if __name__ == "__main__":
    main()
