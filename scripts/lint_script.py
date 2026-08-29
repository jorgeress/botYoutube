"""
Non-blocking linter for faceless YouTube scripts.

Checks each beat for common quality issues and prints warnings.
Does NOT stop the pipeline, run before generate_voice.py to catch problems early.

Usage:
    python scripts/lint_script.py [slug]
    python scripts/lint_script.py          # uses most recent output folder
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import OUTPUT_DIR

try:
    from scripts._catalog import (
        SHOT_TYPES, VALID_EMOTIONS, VALID_POSES, VALID_BGS,
        VALID_SYMBOLS, VALID_POSITIONS, VALID_PROPS, SHOT_ALLOWED_FIELDS,
        VALID_COSTUMES, VALID_TIMES, POSE_EMOTIONS,
    )
    _CATALOG_AVAILABLE = True
except ImportError:
    _CATALOG_AVAILABLE = False


# ── Visual quality signals ─────────────────────────────────────────────────────

# At least one of these should appear in a well-written visual description
_TECHNIQUE_KW = [
    # Technique 1: text label on object
    "labeled", "reading", "text '", "text on", "showing '",
    # Technique 2: text frame
    "text frame", "text reveal", "large bold", "standalone text",
    # Technique 3: floating symbol
    "question mark", "lightbulb", "thought bubble", "brain", "gear",
    "floating", "glowing",
    # Technique 4: concept diagram
    "arrow", "diagram", "symbol", "flow",
    # Technique 5: anatomical / region diagram
    "region", "dotted", "colored area", "cross-section",
    # Technique 6: background color = mood
    "orange background", "dark blue", "earthy", "warm background",
    # Technique 7: costume = role
    "lab coat", "glasses", "lab coat", "costume", "wearing",
    # Technique 8: multi-icon radiance
    "orbiting", "icons around", "surrounding", "floating around",
    # General scene richness
    "stickman", "stickfigure", "chart", "bar chart", "graph",
    "nightstand", "window", "desk", "shelf", "wall", "floor",
    "outdoor", "park", "mountain", "street", "room", "kitchen",
    "bed", "table", "chair", "mirror", "laptop", "book",
]

_CROWD_KW = [
    "group of", "crowd of", "several people", "multiple people",
    "three stickmen", "two stickmen", "many people", "audience of",
    "people around", "stickmen ",
]

_VAGUE_KW = [
    "something", "various things", "misc", "etc", "and more",
    "some items", "other stuff",
]


def _has_technique(visual: str) -> bool:
    v = visual.lower()
    return any(k in v for k in _TECHNIQUE_KW)


def _has_vague_crowd(visual: str) -> bool:
    v = visual.lower()
    return any(k in v for k in _CROWD_KW)


def _is_too_short(visual: str) -> bool:
    return len(visual.strip()) < 18


def _is_vague(visual: str) -> bool:
    v = visual.lower()
    return any(k in v for k in _VAGUE_KW)


def _narration_visual_mismatch(visual: str, narration: str) -> bool:
    """Very basic check: if narration mentions a number but visual has no space hint."""
    has_number = bool(re.search(r'\b\d+\s*%|\b\d{3,}\b|\b(million|billion|thousand)\b',
                                narration, re.IGNORECASE))
    if not has_number:
        return False
    v = visual.lower()
    # Data beats already handled by PIL, no mismatch concern
    data_kw = ["bar chart", "graph", "chart", "diagram", "stat", "data"]
    if any(k in v for k in data_kw):
        return False
    space_hints = ["space", "right side", "clear area", "open", "room for"]
    return not any(k in v for k in space_hints)


# ── Structured beat validator ──────────────────────────────────────────────────

def _lint_structured(beats: list[dict]) -> list[str]:
    """Validate structured beats (fields dict present) against the closed catalogs."""
    warnings: list[str] = []
    last_tf_idx: int = -100      # global beat index of most recent text-frame
    seg_bgs: dict[int, str] = {} # segment_id -> first bg seen in that segment

    for b in beats:
        fields = b.get("fields")
        if fields is None:
            continue  # legacy prose: handled by _lint_prose

        idx    = b.get("index", 0)
        seg_id = b.get("segment_id", 0)
        prefix = f"  beat {idx:03d}"
        shot   = fields.get("shot", "").lower()

        if shot not in SHOT_TYPES:
            warnings.append(f"{prefix}: unknown shot '{shot}' -- must be one of {sorted(SHOT_TYPES)}")
            continue

        allowed = SHOT_ALLOWED_FIELDS.get(shot, frozenset())
        for key in fields:
            if key not in allowed:
                warnings.append(f"{prefix}: field '{key}' not allowed for shot '{shot}'")

        # ── text-frame checks ──────────────────────────────────────────────────
        if shot == "text-frame":
            if isinstance(idx, int) and idx - last_tf_idx < 8:
                warnings.append(f"{prefix}: text-frame too soon after beat {last_tf_idx} "
                                 f"({idx - last_tf_idx} beats gap, need >= 8)")
            last_tf_idx = idx if isinstance(idx, int) else last_tf_idx

            text_val = fields.get("text", "").strip("'\"")
            if not text_val:
                warnings.append(f"{prefix}: text-frame missing text: value")
            else:
                if text_val != text_val.upper():
                    warnings.append(f"{prefix}: text: must be UPPERCASE (got '{text_val}')")
                words = text_val.split()
                if len(words) > 4:
                    warnings.append(f"{prefix}: text: has {len(words)} words, max 4")
                for w in words:
                    if len(w) > 15:
                        warnings.append(f"{prefix}: text: word '{w}' is {len(w)} chars, max 15")
                if not re.match(r'^[A-Z0-9% ]+$', text_val):
                    warnings.append(f"{prefix}: text: has non-ASCII or punctuation (only A-Z, 0-9, %, space)")

        # ── diagram checks ─────────────────────────────────────────────────────
        elif shot == "diagram":
            left  = fields.get("left", "")
            right = fields.get("right", "")
            if left  and left  not in VALID_SYMBOLS:
                warnings.append(f"{prefix}: diagram left: '{left}' not in symbol catalog")
            if right and right not in VALID_SYMBOLS:
                warnings.append(f"{prefix}: diagram right: '{right}' not in symbol catalog")
            if not fields.get("arrow"):
                warnings.append(f"{prefix}: diagram missing arrow: field (must be explicit)")
            bg_val = fields.get("bg", "")
            if bg_val and bg_val not in VALID_BGS:
                warnings.append(f"{prefix}: bg: '{bg_val}' not in catalog")

        # ── scene beat checks (wide / medium / close-up) ──────────────────────
        else:
            char_val    = fields.get("char", "0")
            char_tokens = [t.strip() for t in char_val.split(",")]
            try:
                char_count = int(char_tokens[0])
            except ValueError:
                char_count = 0
                warnings.append(f"{prefix}: char: count '{char_tokens[0]}' must be 0, 1, or 2")
            if char_count > 2:
                warnings.append(f"{prefix}: char count {char_count} exceeds max of 2")

            emotion = "neutral"
            char_costume = "none"
            for tok in char_tokens[1:]:
                tok_l = tok.lower()
                if tok_l.startswith("costume:"):
                    char_costume = tok_l[len("costume:"):].strip()
                elif tok_l:
                    emotion = tok_l

            if emotion not in VALID_EMOTIONS:
                warnings.append(f"{prefix}: emotion '{emotion}' not in catalog")
            if char_costume not in VALID_COSTUMES:
                warnings.append(f"{prefix}: costume '{char_costume}' not in catalog "
                                 f"(valid: {sorted(VALID_COSTUMES)})")

            pose_val = fields.get("pose", "")
            if pose_val:
                if char_count == 0:
                    warnings.append(f"{prefix}: pose: present but char: 0")
                elif pose_val not in VALID_POSES:
                    warnings.append(f"{prefix}: pose '{pose_val}' not in catalog")
                else:
                    # Pose-emotion pairing: a soft hint only. Nano Banana renders any
                    # combination fine, so this no longer blocks (was an ERROR for Flux).
                    allowed = POSE_EMOTIONS.get(pose_val, [])
                    if allowed and emotion not in allowed:
                        warnings.append(
                            f"{prefix}: hint: pose '{pose_val}' + emotion '{emotion}' is an "
                            f"unusual pairing (natural: {', '.join(allowed)}), fine if intended"
                        )

            # v1 single prop
            prop_val = fields.get("prop", "")
            if prop_val:
                prop_tokens = prop_val.split()
                prop_name   = prop_tokens[0]
                prop_pos    = " ".join(prop_tokens[1:]) if len(prop_tokens) > 1 else ""
                if prop_name not in VALID_PROPS:
                    warnings.append(f"{prefix}: prop '{prop_name}' not in catalog")
                if prop_pos and prop_pos not in VALID_POSITIONS:
                    warnings.append(f"{prefix}: prop position '{prop_pos}' not in catalog")

            # v2 multi-prop (props:)
            props_val = fields.get("props", "")
            if props_val:
                props_list = [p.strip() for p in props_val.split(",") if p.strip()]
                if len(props_list) > 2:
                    warnings.append(f"{prefix}: props: has {len(props_list)} props, max 2")
                for pv in props_list:
                    ptokens = pv.split()
                    pname   = ptokens[0]
                    ppos    = " ".join(ptokens[1:]) if len(ptokens) > 1 else ""
                    if pname not in VALID_PROPS:
                        warnings.append(f"{prefix}: props: '{pname}' not in catalog")
                    if ppos and ppos not in VALID_POSITIONS:
                        warnings.append(f"{prefix}: props: position '{ppos}' not in catalog")

            # time field (v2)
            time_val = fields.get("time", "")
            # Attention budget: char + pose + prop + time = 5 active elements; Flux attends to ~3-4
            if (time_val and time_val.lower() not in ("", "none")
                    and char_count >= 1 and pose_val and (prop_val or props_val)):
                warnings.append(
                    f"{prefix}: attention overload: char+pose+prop+time = 5 elements "
                    f"(Flux Schnell attends to ~3-4); remove prop or change bg instead of using time:"
                )
            if time_val and time_val.lower() not in VALID_TIMES:
                warnings.append(f"{prefix}: time: '{time_val}' not valid "
                                 f"(valid: {sorted(VALID_TIMES)})")

            # place field (v2): just check it's not empty if present
            place_val = fields.get("place", "").strip("'\"")
            if place_val and len(place_val.split()) > 3:
                warnings.append(f"{prefix}: place: '{place_val}' has >3 words (max 3)")

            bg_val = fields.get("bg", "")
            if bg_val and bg_val not in VALID_BGS:
                warnings.append(f"{prefix}: bg: '{bg_val}' not in catalog")
            elif bg_val:
                if seg_id not in seg_bgs:
                    seg_bgs[seg_id] = bg_val
                elif seg_bgs[seg_id] != bg_val:
                    warnings.append(f"{prefix}: bg '{bg_val}' breaks segment continuity "
                                     f"(segment {seg_id} started with '{seg_bgs[seg_id]}')")

    return warnings


def _lint_prose(beats: list[dict]) -> list[str]:
    """Validate legacy prose beats (no fields dict)."""
    warnings: list[str] = []
    for b in beats:
        if b.get("fields") is not None:
            continue  # structured: handled above
        idx    = b.get("index", "?")
        visual = b.get("visual", "")
        narr   = b.get("narration", "")
        btype  = b.get("beat_type", "scene")
        prefix = f"  beat {idx:03d}"

        if btype == "text_frame":
            continue

        if _is_too_short(visual):
            warnings.append(f"{prefix}: visual too short ({len(visual)} chars) -- add more scene detail")
        if not _has_technique(visual):
            warnings.append(f"{prefix}: no visual technique detected -- add object, costume, symbol or background")
        if _has_vague_crowd(visual):
            warnings.append(f"{prefix}: crowd description -- Flux often fails crowds, focus on one character")
        if _is_vague(visual):
            warnings.append(f"{prefix}: vague visual language -- be specific about objects and positions")
        if _narration_visual_mismatch(visual, narr):
            warnings.append(f"{prefix}: narration has a number but visual has no space hint")

    return warnings


# ── Global narration checks ───────────────────────────────────────────────────

def _lint_narration(beats: list[dict]) -> list[str]:
    """Checks that apply to every beat's narration text regardless of type."""
    warnings: list[str] = []
    for b in beats:
        idx  = b.get("index", "?")
        narr = b.get("narration", "")
        prefix = f"  beat {idx:03d}"

        if ': ' in narr or '--' in narr:
            snippet = narr[:60]
            warnings.append(
                f"{prefix}: em-dash or '--' in narration: \"{snippet}\" "
                "-- use a comma or period; dashes render as ', ' in subtitles"
            )

        fields = b.get("fields") or {}
        if fields.get("shot") == "text-frame":
            text_val = fields.get("text", "").strip("'\"").lower()
            if text_val and text_val not in narr.lower():
                warnings.append(
                    f"{prefix}: text-frame word '{text_val.upper()}' not found in narration "
                    "-- the narration sentence must say the concept explicitly"
                )

    return warnings


# ── Main ───────────────────────────────────────────────────────────────────────

def lint(beats: list[dict]) -> list[str]:
    warnings: list[str] = []
    if _CATALOG_AVAILABLE:
        warnings.extend(_lint_structured(beats))
    warnings.extend(_lint_prose(beats))
    warnings.extend(_lint_narration(beats))
    return warnings


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders found in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def main():
    slug_arg = next((a for a in sys.argv[1:] if not a.startswith("--")), None)
    slug     = find_slug(slug_arg)
    out_dir  = os.path.join(OUTPUT_DIR, slug)
    seg_path = os.path.join(out_dir, "segments.json")

    if not os.path.exists(seg_path):
        print(f"ERROR: {seg_path} not found. Run parse_script.py first.")
        sys.exit(1)

    with open(seg_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = data["beats"]

    print(f"Linting {len(beats)} beats for: {slug}")
    warnings = lint(beats)

    if not warnings:
        print("  No issues found.")
    else:
        for w in warnings:
            print(f"WARN {w}")
        print(f"\n{len(warnings)} warning(s). Fix before generating clips for best results.")

    return len(warnings)


if __name__ == "__main__":
    sys.exit(main())
