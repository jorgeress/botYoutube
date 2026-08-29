"""
Parses input/script.txt into an ordered list of visual beats and saves segments.json.

Script format (Option A: inline beats):

    TITLE: Why Habits Change Everything

    NARRATION:
    [SEGMENT 1]
    (stickman waking up in bed, alarm clock ringing)
    Every morning, most of us follow the exact same routine.

    (stickman brushing teeth at the bathroom sink)
    Wake up, brush teeth, drink coffee.

    [SEGMENT 2]
    (stickman figure with a glowing brain, gears turning)
    Scientists found that forty percent of our actions are automatic.

Each `(visual)` line + the narration below it = one BEAT. One beat = one image
on screen for exactly as long as its narration is spoken.

Output segments.json:
    {
      "title": ..., "slug": ...,
      "beats": [
        { "index": 0, "segment_id": 1, "visual": "...", "narration": "..." },
        ...
      ]
    }
"""

import re
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import INPUT_SCRIPT, OUTPUT_DIR
from scripts._text_frame import is_text_frame


def parse_fields(visual: str) -> dict | None:
    """
    Parse a structured beat visual string into a dict of fields.
    Returns None if the visual is not structured (does not start with 'shot:').

    Example:
      "shot: medium | char: 1, worried | pose: arms-crossed | prop: red-X right | bg: plain-white"
      -> {"shot": "medium", "char": "1, worried", "pose": "arms-crossed",
          "prop": "red-X right", "bg": "plain-white"}
    """
    stripped = visual.strip()
    if not stripped.lower().startswith("shot:"):
        return None
    fields: dict[str, str] = {}
    for part in stripped.split("|"):
        part = part.strip()
        if not part or ":" not in part:
            continue
        colon_idx = part.index(":")
        key   = part[:colon_idx].strip().lower()
        value = part[colon_idx + 1:].strip()
        fields[key] = value
    return fields


def classify_beat_type(visual: str, fields: dict | None = None) -> str:
    """
    Classify a beat by how it should be rendered.
      text_frame: pure text reveal; PIL only (_text_frame.py)
      diagram: cause→effect diagram; PIL (_diagram_frame.py) or Flux fallback
      scene: everything else; ComfyUI/Flux
    """
    if fields is not None:
        shot = fields.get("shot", "").lower()
        if shot == "text-frame":
            return "text_frame"
        if shot == "diagram":
            return "diagram"
        return "scene"
    if is_text_frame(visual):
        return "text_frame"
    return "scene"


def slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug[:60]


def parse_beats(segment_body: str) -> list[dict]:
    """Extract (visual)/narration beats from one segment body."""
    beat_pattern = re.compile(
        r"^[ \t]*\(([^)]+)\)[ \t]*\n(.*?)(?=^[ \t]*\(|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    beats = []
    for m in beat_pattern.finditer(segment_body):
        visual = m.group(1).strip()
        narration = re.sub(r"\s+", " ", m.group(2)).strip()
        if narration:
            beats.append({"visual": visual, "narration": narration})
    return beats


def parse_script(script_path: str) -> dict:
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()

    title_match = re.search(r"^TITLE:\s*(.+)$", text, re.MULTILINE)
    if not title_match:
        raise ValueError("No TITLE: line found in script.")
    title = title_match.group(1).strip()

    narration_match = re.search(r"NARRATION:\s*(.*)", text, re.DOTALL)
    if not narration_match:
        raise ValueError("No NARRATION: section found in script.")
    narration_body = narration_match.group(1).strip()

    # Split into segments. Header may be just "[SEGMENT 1]" (new format) or
    # "[SEGMENT 1 | VISUAL: ...]" (legacy), we capture any header metadata.
    segment_pattern = re.compile(
        r"\[SEGMENT\s+(\d+)([^\]]*)\]\s*(.*?)(?=\[SEGMENT\s+\d+|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    flat_beats: list[dict] = []
    global_index = 0

    for match in segment_pattern.finditer(narration_body):
        seg_id   = int(match.group(1))
        meta_raw = match.group(2)
        body     = match.group(3).strip()

        beats = parse_beats(body)

        # Legacy fallback: header has "VISUAL:" and no inline beats → one beat
        if not beats and "VISUAL:" in meta_raw.upper():
            visual = ""
            for part in meta_raw.split("|"):
                part = part.strip()
                if part.upper().startswith("VISUAL:"):
                    visual = part[7:].strip()
            narration = re.sub(r"\s+", " ", body).strip()
            if narration:
                beats = [{"visual": visual, "narration": narration}]

        for b in beats:
            fields = parse_fields(b["visual"])
            flat_beats.append({
                "index":      global_index,
                "segment_id": seg_id,
                "beat_type":  classify_beat_type(b["visual"], fields),
                "fields":     fields,
                "visual":     b["visual"],
                "narration":  b["narration"],
            })
            global_index += 1

    if not flat_beats:
        raise ValueError(
            "No beats found. Each segment needs (visual) lines above narration.\n"
            "See prompts/script_template.md for the format."
        )

    return {"title": title, "slug": slugify(title), "beats": flat_beats}


def main():
    script_path = INPUT_SCRIPT
    if not os.path.exists(script_path):
        print(f"ERROR: {script_path} not found. Place your script there first.")
        sys.exit(1)

    result = parse_script(script_path)
    slug = result["slug"]
    out_dir = os.path.join(OUTPUT_DIR, slug)
    os.makedirs(out_dir, exist_ok=True)

    segments_path = os.path.join(out_dir, "segments.json")
    with open(segments_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    n_segments = len({b["segment_id"] for b in result["beats"]})
    print(f"Title   : {result['title']}")
    print(f"Slug    : {slug}")
    print(f"Segments: {n_segments}")
    print(f"Beats   : {len(result['beats'])}  (= images to generate)")
    print(f"Saved   : {segments_path}")
    return result


if __name__ == "__main__":
    main()
