"""
Builds image_prompts.json: one image per beat, timed from the actual
per-beat narration audio so each image is on screen exactly while its
narration is spoken.

Run after generate_voice.py (needs narration_segments/beat_*.mp3).

Usage:
    python scripts/generate_image_prompts.py [slug] [--force]

Output: output/<slug>/image_prompts.json
  [{ index, start, end, duration_seconds, segment_id, beat_type,
     visual, narration, image_prompt, _overlay, generated, image_path }, ...]

Architecture: PIL / Flux separation (non-overlapping responsibilities):
  Flux draws: scene, characters, backgrounds, props, composition
  PIL draws:  text, numbers, charts, timelines, labels (_overlay.py)
  text_frame beats: PIL renders the whole image, Flux is not called
"""

import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    BEAT_MAX_IMAGE_DURATION_S,
    BEAT_SILENCE_MS,
    SEGMENT_SILENCE_MS,
    IMAGE_STYLE_ANCHOR,
    IMAGE_ANTI_QUALITY,
    ACTIVE_STYLE,
    CLIP_SOURCE,
    OUTPUT_DIR,
)
from scripts._text_frame import is_text_frame
try:
    from scripts._catalog import (
        CHARACTER_ANCHOR, STYLE_ANCHOR, EMOTION, POSE, BG,
        SYMBOL, PROP_FRAGMENT, PROP_POSITION, ARROW_DIRECTION, ARROW_COLOR,
        COSTUME, TIME_BG_FRAGMENT,
        GEMINI_STYLE_ID, GEMINI_CHARACTER_ONE, GEMINI_CHARACTER_TWO,
        GEMINI_NO_CHARACTER, GEMINI_COMPOSITION, GEMINI_ANTI_DUP, GEMINI_SHOT_FRAMING,
    )
    _CATALOG_AVAILABLE = True
except ImportError:
    _CATALOG_AVAILABLE = False

# Backends that reward rich natural-language prompts (literal scene descriptions)
# instead of Flux comma-soup. Routes build_entries() to build_gemini_prompt().
# "manual" = same Nano Banana prompts, pasted by hand into AI Studio.
_NL_PROMPT_BACKENDS = {"gemini", "manual"}

try:
    from scripts._diagram_frame import can_render as _diagram_can_render
    _DIAGRAM_AVAILABLE = True
except Exception:
    _DIAGRAM_AVAILABLE = False


def measure_duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def load_beat_timings(out_dir: str) -> dict[int, dict] | None:
    """
    Load the authoritative per-beat timeline written by generate_voice.py.
    Returns {beat_index: {start, duration, gap_after}} or None if absent (legacy).
    Using it guarantees images/subtitles share the exact offsets of the gapless audio.
    """
    path = os.path.join(out_dir, "beat_timings.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return {b["index"]: b for b in data.get("beats", [])}
    except Exception:
        return None


_WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}


def _extract_number_label(narration: str) -> str | None:
    """Return a short displayable stat string if narration contains a notable number."""
    n = narration.lower()
    m = re.search(r'(\d+)\s*%', narration)
    if m:
        return f"{m.group(1)}%"
    m = re.search(r'(\d+)\s+percent', narration, re.IGNORECASE)
    if m:
        return f"{m.group(1)}%"
    for word, num in _WORD_TO_NUM.items():
        # require word preceded by space/start (not a hyphen like "sixty-five")
        if re.search(rf'(?:^|[\s,]){word}\s+percent\b', n):
            return f"{num}%"
    m = re.search(r'(\d[\d,]*)\s*(million|billion|thousand)', narration, re.IGNORECASE)
    if m:
        suffix = {"million": "M", "billion": "B", "thousand": "K"}[m.group(2).lower()]
        return f"{m.group(1)}{suffix}"
    m = re.search(r'\b(\d{3,})\b', narration)
    if m:
        return m.group(1)
    return None


def _build_overlay_meta(visual: str, narration: str,
                        num_label: str | None, beat_type: str = "scene") -> dict:
    return {}


def build_prompt_from_fields(fields: dict) -> str:
    """
    Build a Flux prompt from structured beat fields.
    Fixed assembly order: char-anchor+emotion -> pose -> prop -> bg -> style-anchor.
    Returns "" for text-frame beats (PIL renders those).
    """
    if not _CATALOG_AVAILABLE:
        return ""

    shot = fields.get("shot", "").lower()

    if shot == "text-frame":
        return ""

    parts: list[str] = []

    if shot == "diagram":
        left_sym  = fields.get("left", "")
        right_sym = fields.get("right", "")
        arrow_val = fields.get("arrow", "right red")
        bg_val    = fields.get("bg", "plain-white")

        arrow_tokens = arrow_val.split()
        arrow_dir    = arrow_tokens[0] if arrow_tokens else "right"
        arrow_col    = arrow_tokens[1] if len(arrow_tokens) > 1 else "red"

        left_frag  = SYMBOL.get(left_sym,  left_sym.replace("-", " "))
        right_frag = SYMBOL.get(right_sym, right_sym.replace("-", " "))
        col_frag   = ARROW_COLOR.get(arrow_col, "bold")
        dir_frag   = ARROW_DIRECTION.get(arrow_dir, "pointing right")

        # TAREA 0 fix: wrap symbols as hand-drawn sketches so Flux matches stickman style
        # instead of falling back to flat vector clipart (which it does without a character)
        parts.append(f"hand-drawn ink sketch of {left_frag} on the left")
        parts.append(f"{col_frag} arrow {dir_frag}")
        parts.append(f"hand-drawn ink sketch of {right_frag} on the right")
        parts.append(BG.get(bg_val, "plain pure white background"))
        parts.append("no human figures, no stickmen")
        parts.append(f"hand-drawn ink sketch style, rough black lines, {STYLE_ANCHOR}")
        return ", ".join(p for p in parts if p)

    # scene beats (wide / medium / close-up)
    char_val = fields.get("char", "0")
    pose_val = fields.get("pose", "")
    bg_val   = fields.get("bg", "plain-white")
    time_val = fields.get("time", "none").lower()
    place_val = fields.get("place", "").strip("'\"")

    # Parse char tokens: "1, neutral" or "1, neutral, costume: lab-coat"
    char_tokens = [t.strip() for t in char_val.split(",")]
    try:
        char_count = int(char_tokens[0])
    except ValueError:
        char_count = 0
    char_emotion = "neutral"
    char_costume = "none"
    for tok in char_tokens[1:]:
        tok_l = tok.lower()
        if tok_l.startswith("costume:"):
            char_costume = tok_l[len("costume:"):].strip()
        elif tok_l:
            char_emotion = tok_l

    # Props: v2 "props: book-held, clock-right" (up to 2) or v1 "prop: clock right"
    props_raw = fields.get("props", "")
    prop_raw  = fields.get("prop", "")
    props_list: list[str] = []
    if props_raw:
        for p in props_raw.split(","):
            p = p.strip()
            if p:
                props_list.append(p)
        props_list = props_list[:2]  # hard budget: max 2
    elif prop_raw:
        props_list = [prop_raw]

    if char_count >= 1:
        count_word = "single" if char_count == 1 else "two"
        parts.append(f"{count_word} stickman figure, {CHARACTER_ANCHOR}")
        emotion_frag = EMOTION.get(char_emotion, "")
        if emotion_frag:
            parts.append(emotion_frag)
        if pose_val:
            parts.append(POSE.get(pose_val, pose_val.replace("-", " ")))
        if char_costume and char_costume != "none":
            costume_frag = COSTUME.get(char_costume, "")
            if costume_frag:
                parts.append(costume_frag)
    else:
        parts.append("no human figures, no stickmen, objects only")

    for pv in props_list:
        prop_tokens = pv.split()
        prop_name   = prop_tokens[0]
        prop_pos    = " ".join(prop_tokens[1:]) if len(prop_tokens) > 1 else ""
        prop_frag   = PROP_FRAGMENT.get(prop_name, prop_name.replace("-", " "))
        pos_frag    = PROP_POSITION.get(prop_pos, "")
        parts.append(f"{prop_frag} {pos_frag}".strip())

    # time: evening/night add a Flux bg fragment; morning/afternoon go to sprites only
    time_frag = TIME_BG_FRAGMENT.get(time_val, "")
    if time_val == "night":
        bg_val = "night"   # override declared bg
    elif time_frag:
        parts.append(time_frag)

    # place: building outline with blank sign, PIL writes the text in _comfyui.py
    if place_val:
        parts.append("simple building outline in the background with a blank rectangular sign")

    parts.append(BG.get(bg_val, "plain pure white background"))
    parts.append(STYLE_ANCHOR)
    return ", ".join(p for p in parts if p)


# ── Gemini / Nano Banana natural-language prompt builder ──────────────────────
# Used when CLIP_SOURCE is a natural-language backend. Prefers the literal `desc:`
# field (the source of scene specificity); falls back to a natural sentence built
# from the closed catalog so legacy scripts (no desc) still render decently.

def _gemini_scene_body_from_fields(fields: dict) -> str:
    """Build a natural-language scene body from catalog fields (desc fallback)."""
    char_val = fields.get("char", "0")
    tokens   = [t.strip() for t in char_val.split(",")]
    try:
        count = int(tokens[0])
    except ValueError:
        count = 0

    emotion = "neutral"
    costume = "none"
    for t in tokens[1:]:
        tl = t.lower()
        if tl.startswith("costume:"):
            costume = tl[len("costume:"):].strip()
        elif tl:
            emotion = tl

    bits: list[str] = []
    if count >= 1:
        subject = "The stickman" if count == 1 else "Two stickmen"
        pose_frag = POSE.get(fields.get("pose", ""), fields.get("pose", "").replace("-", " "))
        bits.append(f"{subject} {pose_frag}.".replace("  ", " ") if pose_frag else f"{subject}.")
        emo_frag = EMOTION.get(emotion, "")
        if emo_frag:
            bits.append(f"Expression: {emo_frag}.")
        cos_frag = COSTUME.get(costume, "")
        if cos_frag:
            bits.append(f"{cos_frag.capitalize()}.")
    else:
        bits.append("No character: objects only.")

    prop_raw = fields.get("prop", "") or fields.get("props", "")
    if prop_raw:
        first = prop_raw.split(",")[0].strip().split()
        pname = first[0] if first else ""
        ppos  = " ".join(first[1:]) if len(first) > 1 else ""
        pfrag = PROP_FRAGMENT.get(pname, pname.replace("-", " "))
        posf  = PROP_POSITION.get(ppos, ppos)
        bits.append(f"A {pfrag} {posf}.".replace("  ", " ").strip())

    return " ".join(bits)


def build_gemini_prompt(beat_type: str, fields: dict | None, narration: str, visual: str) -> str:
    """
    Build a rich natural-language prompt for a hosted image model (Nano Banana).
    Prefers fields['desc'] (literal scene); falls back to catalog assembly.
    Produces a non-empty prompt for every beat type, including text-frame/diagram.
    """
    fields = fields or {}
    desc   = (fields.get("desc") or "").strip().strip("'\"")
    shot   = fields.get("shot", "").lower()

    if beat_type == "text_frame":
        text_val = fields.get("text", "").strip("'\"")
        parts = [
            "Minimal hand-drawn explainer title card, black ink on white, flat style, 16:9.",
            f'Large bold hand-drawn text reading "{text_val}" centered in the upper half.',
        ]
        if desc:
            parts.append(f"Below the text, one small simple illustration: {desc}.")
        return " ".join(parts)

    if beat_type == "diagram":
        if desc:
            body = desc
        else:
            left      = fields.get("left", "")
            right     = fields.get("right", "")
            arrow_tok = fields.get("arrow", "right red").split()
            arrow_col = arrow_tok[1] if len(arrow_tok) > 1 else "red"
            left_frag  = SYMBOL.get(left,  left.replace("-", " "))
            right_frag = SYMBOL.get(right, right.replace("-", " "))
            body = (f"On the left a {left_frag}; on the right a {right_frag}; "
                    f"between them one single bold {arrow_col} arrow pointing left to right, "
                    f"one arrowhead only.")
        return ("Hand-drawn explainer diagram, black ink on white, flat minimal style, 16:9. "
                f"{body} No human figures.")

    # scene beats (wide / medium / close-up)
    framing = GEMINI_SHOT_FRAMING.get(shot, "")
    body    = desc if desc else _gemini_scene_body_from_fields(fields)
    body    = body.rstrip(" .") + "."  # one clean sentence

    # Character clause is chosen by char count so object-only beats (char: 0) never
    # get a stray stickman injected by the style preamble.
    try:
        char_count = int(str(fields.get("char", "0")).split(",")[0].strip())
    except ValueError:
        char_count = 0
    if char_count >= 2:
        char_clause = GEMINI_CHARACTER_TWO
    elif char_count == 1:
        char_clause = GEMINI_CHARACTER_ONE
    else:
        char_clause = GEMINI_NO_CHARACTER

    bg_val   = fields.get("bg", "plain-white")
    if fields.get("time", "none").lower() == "night":
        bg_val = "night"
    bg_frag  = BG.get(bg_val, "plain white background")

    parts = [GEMINI_STYLE_ID, char_clause, framing, body,
             f"Setting: {bg_frag}.", GEMINI_COMPOSITION, GEMINI_ANTI_DUP]
    return " ".join(p for p in parts if p)


_TEXT_FRAME_SPRITE_MAP: list[tuple[list[str], str, str, float]] = [
    (["DOPAMINE", "BRAIN", "NEURON", "NEURAL", "MIND"],              "brain-small",    "top-center", 0.12),
    (["LOOP", "CYCLE", "CRAVING", "SPIRAL", "CIRCULAR", "AVOIDANCE"],"circular-arrow", "top-center", 0.11),
    (["HABIT", "ROUTINE", "PATTERN", "REPEAT", "PROCRASTINAT"],      "circular-arrow", "top-center", 0.11),
    (["REWARD", "GOAL", "WIN", "SUCCESS", "PRIZE"],                  "star",           "top-center", 0.10),
    (["SLEEP", "REST", "TIRED", "FATIGUE"],                          "zzz",            "top-center", 0.10),
    (["QUESTION", "WHY", "HOW", "WHAT", "WONDER"],                   "question-mark",  "top-center", 0.11),
    (["IDEA", "INSIGHT", "DISCOVERY", "THINK", "GROWTH"],            "lightbulb",      "top-center", 0.11),
    (["MINUTE", "TIMER", "CLOCK", "DEADLINE", "TWO MINUTE"],         "clock-small",    "top-center", 0.10),
    (["ALERT", "WARNING", "DANGER", "RISK"],                         "exclamation",    "top-center", 0.10),
    (["HEART", "LOVE", "HEALTH", "CARE"],                            "heart",          "top-center", 0.10),
    (["CHECK", "DONE", "COMPLETE", "SOLVED", "YES"],                 "check",          "top-center", 0.10),
]


def build_sprites(fields: dict | None, narration: str, seed: int) -> list[dict]:
    """
    Derive sprite overlays for a beat from its fields and narration.
    Returns list of {name, anchor, scale} dicts consumed by _sprites.composite_sprites().
    Anti-collision: max 2 sprites per beat, no two on the same anchor.
    """
    sprites: list[dict] = []
    anchors_used: set[str] = set()

    def _try_add(name: str, anchor: str, scale: float) -> None:
        if len(sprites) >= 2 or anchor in anchors_used:
            return
        sprites.append({"name": name, "anchor": anchor, "scale": scale})
        anchors_used.add(anchor)

    # Text-frame beats: inject a thematic sprite from the text keyword.
    # Return immediately: no narration-driven sprites on text cards (redundant).
    if fields and fields.get("shot") == "text-frame":
        text_val = fields.get("text", "").strip("'\"").upper()
        for keywords, sprite_name, anchor, scale in _TEXT_FRAME_SPRITE_MAP:
            if any(kw in text_val for kw in keywords):
                _try_add(sprite_name, anchor, scale)
                break
        return sprites

    # Field-driven sprites (time-of-day)
    if fields:
        time_val = fields.get("time", "none").lower()
        if time_val == "morning":
            _try_add("sun", "top-right", 0.09)
        elif time_val == "afternoon":
            _try_add("clock-small", "top-right", 0.08)

    # Narration-driven sprites: checked in priority order (first match at an anchor wins)
    n = narration.lower()

    # Alarm / threat / dread → exclamation (urgent visual cue)
    if any(k in n for k in ["alarm", "threat", "dread", "classifying it as",
                              "treats it like a", "fear of", "raises an alarm"]):
        _try_add("exclamation", "top-center", 0.10)

    # Guilt / discomfort / emotional avoidance → thought-bubble (before loop/habit check)
    if any(k in n for k in ["guilt", "discomfort", "a feeling", "emotion-regulation",
                              "feels wrong", "feel wrong"]):
        _try_add("thought-bubble", "top-center", 0.10)

    # Loop / cycle / stuck / habit → circular-arrow
    if any(k in n for k in ["the loop", "loop that", "stuck on", "year after year",
                              "same goals", " habit", "habit loop", "routine",
                              "every day", "over and over", "same routine"]):
        _try_add("circular-arrow", "top-center", 0.11)

    # Discovery / research → lightbulb (above character's head)
    if any(k in n for k in ["discovered", "found that", "realized", "it turns out",
                              "research shows", "studies show", "science says"]):
        _try_add("lightbulb", "above-char", 0.12)

    # Question / wonder → question-mark (above character's head)
    if any(k in n for k in ["why ", "what if", "how did", "how do", "wonder", "?"]):
        _try_add("question-mark", "above-char", 0.10)

    # Phone / avoidance / fastest escape → red-x (negative action indicator)
    if any(k in n for k in ["phone", "scroll", "fastest exit", "escape from",
                              "avoid the task", "avoid a feeling", "open your phone",
                              "avoidance works"]):
        _try_add("red-x", "top-center", 0.09)

    # Success / follow-through / completion → check
    if any(k in n for k in ["triples", "follow-through", "breaks the loop",
                              "break it", "relief", "works out"]):
        _try_add("check", "top-center", 0.09)

    # Sleep → zzz (only when emotion/pose are compatible)
    if any(k in n for k in ["sleep", "asleep", "while sleeping"]):
        char_val = (fields or {}).get("char", "")
        char_emotion = next(
            (t.strip().lower() for t in char_val.split(",")[1:]
             if t.strip().lower() in ("happy", "surprised")),
            None,
        )
        pose_val = (fields or {}).get("pose", "")
        if char_emotion not in ("happy", "surprised") and pose_val != "arms-raised":
            _try_add("zzz", "above-char", 0.09)

    # Anti-collision with Flux props: don't put sprite on same visual region as prop
    if fields:
        prop_str = fields.get("prop", fields.get("props", ""))
        if "above" in prop_str:
            sprites = [s for s in sprites if s["anchor"] != "above-char"]
        if "right" in prop_str:
            sprites = [s for s in sprites if s["anchor"] not in ("top-right", "right-mid")]

    return sprites


def enrich_visual(visual: str, narration: str = "") -> str:
    """
    Add composition, scene-type, and visual-language hints to the raw visual.
    Flux draws everything: text, numbers, scenes. We guide it with context hints.
    """
    if is_text_frame(visual):
        return visual

    v = visual.lower()
    n = narration.lower()

    # ── Scene type ────────────────────────────────────────────────────────────
    prehistoric_kw = ["ancient", "prehistoric", "cave", "hunter", "gatherer", "caveman",
                      "neanderthal", "early human", "homo ", "primitive", "stone age",
                      "tribe", "tribal", "ancestors"]
    night_kw       = ["at night", "night sky", "campfire", "bonfire", " stars", "moon ",
                      "nocturnal", "dark outside", "sleeping outside", "nighttime"]
    sleep_kw       = ["sleep", "sleeping", "asleep", "bed ", "bedroom", "dream"]
    lab_kw         = ["lab", "laboratory", "microscope", "test tube", "beaker", "experiment",
                      "scientist", "researcher", "professor", "science class"]
    outdoor_kw     = ["outside", "outdoor", "park", "street", "mountain", "forest", "field",
                      "road", "river", "landscape", "staircase", "climb", "horizon"]
    abstract_kw    = ["brain", "gear", "gears", "arrow", "chart", "percentage",
                      "energy", "battery", "signal", "wave", "orbit", "diagram", "icon",
                      "symbol", "question mark", "lightbulb", "concept diagram"]
    indoor_kw      = ["kitchen", "bathroom", "table", "sink", "chair", "desk", "room",
                      "window", "mirror", "wall", "shelf", "sofa", "couch", "office",
                      "hallway", "door", "classroom", "library", "hospital"]

    is_prehistoric = any(k in v for k in prehistoric_kw)
    is_night       = any(k in v for k in night_kw)
    is_sleep       = any(k in v for k in sleep_kw) and not is_night
    is_lab         = any(k in v for k in lab_kw)
    is_outdoor     = any(k in v for k in outdoor_kw) and not is_prehistoric and not is_night
    is_abstract    = any(k in v for k in abstract_kw)
    is_indoor      = any(k in v for k in indoor_kw) and not is_lab and not is_sleep

    # Explicit darkness: visual says there is no sun / complete darkness
    _darkness_kw = ["complete darkness", "no sun", "pitch black", "total darkness",
                    "all dark", "sky would switch off", "sky off"]
    has_explicit_darkness = any(k in v for k in _darkness_kw)

    # No human character in visual, diagram/object-only beat
    _char_present_kw = ["stickman", "stick figure", "figure", "person", "character",
                        "scientist", "researcher", "teacher", "child", "crowd",
                        "people", "human", "kid"]
    has_any_char = any(k in v for k in _char_present_kw)

    # ── Semantic signals (narration-driven) ───────────────────────────────────
    question_kw = ["why ", "what if", "how did", "how do", "wonder", "mystery",
                   "unknown", "could ", "?", "did they", "do we", "really"]
    idea_kw     = ["discover", "found that", "realized", "insight", "key is",
                   "answer", "solution", "breakthrough", "it turns out"]
    thinking_kw = ["imagin", "pictur", "vision", "thought of", "dream of", "mental"]
    compare_kw  = ["compared to", "versus", "more than double", "unlike",
                   "the difference between", "in contrast", "side by side", "vs "]
    process_kw  = ["step one", "step two", "step three", "first step", "three steps",
                   "phase 1", "phase one", "in sequence", "in order to", "the process"]
    scale_kw    = ["the size of a", "as big as a", "as small as a", "times bigger than",
                   "times smaller than", "compared to a ", "about the size"]

    has_question = any(k in n for k in question_kw)
    has_idea     = any(k in n for k in idea_kw)
    has_thinking = any(k in v for k in thinking_kw) and "bubble" not in v
    has_compare  = any(k in n or k in v for k in compare_kw)
    has_process  = any(k in n or k in v for k in process_kw)
    has_scale    = any(k in n for k in scale_kw)

    # ── Character emotion (face matches narration tone) ───────────────────────
    threat_kw    = ["threat", "danger", "scare", "fear", "anxiet", "alarm",
                    "dread", "worr", "resist", "attack", "treats it like"]
    struggle_kw  = ["struggle", "exhausted", "draining", "sharply", "costs",
                    "difficult", "overwhelm", "painful", "frustrat"]
    happy_kw     = ["happy", "joy", "celebrat", "success", "feels like routine",
                    "proud", "wonderful", "positive", "reclassif", "familiar again"]
    discovery_kw = ["discover", "found that", "realized", "turn out",
                    "breakthrough", "it turns out", "research shows", "tracked"]

    has_threat    = any(k in n for k in threat_kw)
    has_struggle  = any(k in n for k in struggle_kw) and not has_threat
    has_happy     = any(k in n for k in happy_kw) and not has_threat and not has_struggle
    has_discovery = any(k in n for k in discovery_kw)

    has_thousands = bool(re.search(r'thousands?\s+of|hundreds?\s+of\s+participants|many\s+thousands', n))
    has_price     = bool(re.search(r'\bprice\b|\bcharges?\b|\btransition\s+tax\b|\bpay\s+(?:it\s+)?once\b', n))

    year_m   = re.search(r'\b(1[0-9]{3}|20[0-2][0-9])\b', n)
    has_year = bool(year_m)

    # ── Time of day (sync rule 2) ─────────────────────────────────────────────
    _morning_kw   = ["in the morning", "early in the day", "each morning",
                     "every morning", "morning,", "mornings,",
                     "wake up", "waking up", "start of the day"]
    _afternoon_kw = ["mid-afternoon", "by afternoon", "afternoon,",
                     "after lunch", "midday", "mid day", "by mid-afternoon"]
    _evening_kw   = ["in the evening", "by evening", "early evening", "evening,"]
    is_morning   = (not is_night and not is_sleep
                    and any(k in n for k in _morning_kw))
    is_afternoon = (not is_night and not is_sleep
                    and any(k in n for k in _afternoon_kw))
    is_evening   = (not is_night and not is_sleep
                    and any(k in n for k in _evening_kw))

    # ── Role / costume ────────────────────────────────────────────────────────
    scientist_char = any(k in v for k in
                         ["scientist", "researcher", "professor", "expert", "doctor",
                          "lab coat", "laboratory"])
    ancient_char   = any(k in v for k in
                         ["ancient human", "cave person", "hunter", "gatherer", "caveman",
                          "neanderthal", "early human", "tribe member"])
    teacher_char   = any(k in v for k in ["teacher", "professor pointing", "chalkboard",
                                           "whiteboard", "classroom", "lecture"])
    child_char     = any(k in v for k in ["child", "baby", "toddler", "kid ", "young child",
                                           "infant"])

    # ── Single-character enforcement ──────────────────────────────────────────
    # If the visual describes exactly one character and no group, enforce it in prompt.
    crowd_kw  = ["group of", "crowd", "stickmen ", "two stickmen", "several people",
                 "multiple people", "three stickmen", "people around", "audience"]
    single_kw = ["stickman", "stickman figure", "stickman person", "researcher stickman",
                 "a stickman", "one stickman"]
    has_crowd  = any(k in v for k in crowd_kw)
    has_single = any(k in v for k in single_kw) and not has_crowd

    # ── Build prompt ──────────────────────────────────────────────────────────
    parts = [visual]

    # No-character beats: prevent Flux from adding stickmen to diagram/object scenes
    if not has_any_char:
        parts.append("no human figures, no stickmen, objects and diagram only")

    # Floating symbols (Flux draws these well)
    if has_question and not is_abstract:
        parts.append("large bold hand-drawn question mark floating upper right of character")
    elif has_idea:
        parts.append("small glowing yellow hand-drawn lightbulb floating near character's head")
    if has_thinking:
        parts.append("hand-drawn thought bubble rising above character's head")

    # Comparison layout
    if has_compare and not is_abstract:
        parts.append("clear visual split into two halves for comparison, each side labeled")

    # Process/steps
    if has_process and not has_question and not has_idea and not is_abstract:
        parts.append("numbered steps 1 2 3 shown horizontally with arrows between them")

    # Scale comparison
    if has_scale:
        parts.append("two objects side by side at correct relative sizes with size labels below")

    # Costumes
    if scientist_char and "lab coat" not in v and "coat" not in v:
        parts.append("character wearing white lab coat and round glasses")
    if ancient_char and "hair" not in v:
        parts.append("character with messy dark hair, simple rough clothing")
    if teacher_char and "chalk" not in v and "pointing" not in v:
        parts.append("character holding chalk, pointing at board")
    if child_char and "small" not in v:
        parts.append("character drawn much smaller than adult stickman, simple proportions")

    # Single-character enforcement
    if has_single:
        parts.append("single stickman only, no background characters, no bystanders")

    # Character emotion hint: only when a single main character is present
    if has_single or scientist_char or teacher_char or child_char:
        if has_threat:
            parts.append("character with frowning worried expression, furrowed brows, small sweat drop near head")
        elif has_struggle:
            parts.append("character with strained frustrated expression, effort lines drawn around them")
        elif has_happy:
            parts.append("character with big smile, relaxed open posture, arms slightly open")
        elif has_discovery:
            parts.append("character with wide surprised eyes, eyebrows raised, curious expression")

    # Quantity signal: thousands of participants → visible crowd indicator
    if has_thousands:
        parts.append("crowd of many small simplified stick figures in background, '1000+' label visible")

    # Price / cost → subtle money icon
    if has_price and "money" not in v and "bill" not in v and "coin" not in v:
        parts.append("small hand-drawn dollar bill or coin icon floating near character")

    # Time of day hints (sync rule 2), only when no scene already implies time
    if is_morning:
        parts.append("small sun drawn in upper corner, warm morning light")
    elif is_afternoon:
        parts.append("clock on wall showing 2pm, bright daylight")
    elif is_evening:
        parts.append("warm amber light from window, early evening")

    # Institution / location (sync rule 3)
    inst_m = re.search(
        r'(?:at|from|researchers?\s+at|study(?:ing)?\s+at)\s+'
        r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})',
        narration,  # original case -- proper nouns
    )
    if inst_m:
        inst = inst_m.group(1).strip()
        if inst and len(inst) < 35 and inst.lower() not in v:
            parts.append(f"simple building outline in background with sign reading '{inst}'")

    # Scene background: style-aware: Style B anchor already defines dark bg, avoid conflict
    _b = ACTIVE_STYLE == "B"
    if is_prehistoric:
        parts.append("sandy orange-brown ground, warm earthy orange background tone")
    elif is_night:
        if has_explicit_darkness:
            parts.append("pitch black sky, absolutely no sun or moon visible, only faint tiny white dot stars scattered, complete darkness except starlight")
        else:
            parts.append("dark blue night sky background, small white dot stars scattered")
    elif is_sleep:
        parts.append("dark blue bedroom background, simple bed silhouette")
    elif is_lab:
        if _b:
            parts.append("simple dark floor platform, muted background")
        else:
            parts.append("white background, simple light gray floor platform")
    elif is_outdoor:
        parts.append("green grass strip at bottom, light sky above, wide shot")
    elif is_abstract:
        if _b:
            parts.append("centered composition, large simplified icons, dark background")
        else:
            parts.append("white background, centered composition, large simplified icons")
    elif is_indoor:
        parts.append("simple warm interior, thin floor line, wide shot")
    else:
        if _b:
            parts.append("thin ground line at bottom")
        else:
            parts.append("pure white background, thin ground line at bottom")

    parts.append("clear single focal point, no clutter, only what is described")

    return ", ".join(parts)


def build_prompt(visual: str, narration: str = "") -> str:
    enriched = enrich_visual(visual, narration)
    return f"{enriched}, {IMAGE_STYLE_ANCHOR}, {IMAGE_ANTI_QUALITY}"


def find_slug(slug_arg: str | None) -> str:
    if slug_arg:
        return slug_arg
    entries = [e for e in os.scandir(OUTPUT_DIR) if e.is_dir()]
    if not entries:
        raise FileNotFoundError(f"No output folders found in {OUTPUT_DIR}/")
    return max(entries, key=lambda e: e.stat().st_mtime).name


def build_entries(beats: list[dict], out_dir: str) -> list[dict]:
    seg_dir = os.path.join(out_dir, "narration_segments")
    timings = load_beat_timings(out_dir)  # authoritative timeline, or None (legacy)
    entries: list[dict] = []
    cursor = 0.0
    idx = 0
    seg_beat_count: dict[int, int] = {}  # segment_id -> beats seen so far

    for i, beat in enumerate(beats):
        mp3 = os.path.join(seg_dir, f"beat_{beat['index']:03d}.mp3")
        t = timings.get(beat["index"]) if timings else None
        if t is not None:
            dur        = t["duration"]
            beat_start = t["start"]
        else:
            if not os.path.exists(mp3):
                raise FileNotFoundError(f"Beat MP3 not found: {mp3}\nRun generate_voice.py first.")
            dur        = measure_duration(mp3)
            beat_start = cursor
        beat_end = beat_start + dur

        seg_id = beat["segment_id"]

        # Backwards compatibility: beat_type may not be in old segments.json
        beat_type = beat.get("beat_type") or (
            "text_frame" if is_text_frame(beat["visual"]) else "scene"
        )

        # Structured beat routing: fields dict present -> use field->fragment mapping
        fields = beat.get("fields")  # None for legacy prose beats
        narration_text = beat.get("narration", "")

        nl_backend = CLIP_SOURCE.lower() in _NL_PROMPT_BACKENDS

        if nl_backend and _CATALOG_AVAILABLE:
            # Hosted model (Nano Banana): rich natural-language prompt for EVERY beat
            # type: text-frame/diagram are image-generated too (illustrated frames),
            # not the PIL renders used by the local ComfyUI path.
            prompt = build_gemini_prompt(beat_type, fields, narration_text, beat["visual"])
        elif beat_type == "text_frame":
            prompt = ""
        elif beat_type == "diagram" and _DIAGRAM_AVAILABLE and fields and _diagram_can_render(fields):
            # TAREA 5: PIL renders diagram, no Flux prompt needed
            prompt = ""
        elif fields is not None:
            prompt = build_prompt_from_fields(fields) if _CATALOG_AVAILABLE else build_prompt(beat["visual"], narration_text)
        else:
            prompt = build_prompt(beat["visual"], narration_text)

        # Safety: split a long beat into multiple images of the same visual.
        # text_frame and diagram PIL renders are deterministic, skip split (identical duplicates).
        n_imgs = max(1, int(dur // BEAT_MAX_IMAGE_DURATION_S) +
                     (1 if dur % BEAT_MAX_IMAGE_DURATION_S > 0.5 else 0))
        if beat_type in ("text_frame", "diagram"):
            n_imgs = 1
        # Hosted backends generate a fresh (different) image per call, so a split would
        # cause a visual jump mid-sentence and burn extra quota, one image per beat.
        if nl_backend:
            n_imgs = 1
        step = dur / n_imgs

        # Per-segment seed: beats in the same segment share a style base.
        beat_idx_in_seg = seg_beat_count.get(seg_id, 0)
        seg_beat_count[seg_id] = beat_idx_in_seg + 1
        seg_base = int(hashlib.sha256(f"{out_dir}:{seg_id}".encode()).hexdigest(), 16)
        beat_seed = (seg_base + beat_idx_in_seg) % (2**32)

        beat_sprites = build_sprites(fields, narration_text, beat_seed)

        for k in range(n_imgs):
            s = beat_start + k * step
            e = beat_start + (k + 1) * step if k < n_imgs - 1 else beat_end
            entries.append({
                "index":            idx,
                "start":            round(s, 3),
                "end":              round(e, 3),
                "duration_seconds": round(e - s, 3),
                "segment_id":       seg_id,
                "beat_type":        beat_type,
                "visual":           beat["visual"],
                "narration":        narration_text,
                "image_prompt":     prompt,
                "fields":           fields,
                "_sprites":         beat_sprites,
                "seed":             (beat_seed + k) % (2**32),
                "generated":        False,
                "image_path":       None,
            })
            idx += 1

        # Advance cursor by the same gap generate_voice.py inserted after this beat.
        # With beat_timings.json the gap is authoritative; otherwise reconstruct it.
        if t is not None:
            cursor = beat_end + t["gap_after"]
        elif i < len(beats) - 1:
            same_segment = beats[i]["segment_id"] == beats[i + 1]["segment_id"]
            gap_ms = BEAT_SILENCE_MS if same_segment else SEGMENT_SILENCE_MS
            cursor = beat_end + gap_ms / 1000.0
        else:
            cursor = beat_end

    # Make contiguous: silences absorbed into preceding image, video = narration length exactly
    narration_mp3 = os.path.join(out_dir, "narration.mp3")
    total_dur = measure_duration(narration_mp3) if os.path.exists(narration_mp3) else None
    for i, e in enumerate(entries):
        if i + 1 < len(entries):
            e["end"] = entries[i + 1]["start"]
        elif total_dur is not None:
            e["end"] = round(total_dur, 3)
        e["duration_seconds"] = round(e["end"] - e["start"], 3)

    return entries


def main():
    args = sys.argv[1:]
    force = "--force" in args
    slug_arg = next((a for a in args if not a.startswith("--")), None)
    slug = find_slug(slug_arg)
    out_dir = os.path.join(OUTPUT_DIR, slug)

    prompts_path = os.path.join(out_dir, "image_prompts.json")
    if os.path.exists(prompts_path) and not force:
        with open(prompts_path) as f:
            existing = json.load(f)
        done = sum(1 for e in existing if e.get("generated"))
        print(f"image_prompts.json exists ({len(existing)} entries, {done} generated). Use --force to regenerate.")
        return

    segments_path = os.path.join(out_dir, "segments.json")
    if not os.path.exists(segments_path):
        print(f"ERROR: {segments_path} not found. Run parse_script.py first.")
        sys.exit(1)

    with open(segments_path, encoding="utf-8") as f:
        data = json.load(f)
    beats = data["beats"]

    entries = build_entries(beats, out_dir)

    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    total_dur = entries[-1]["end"] if entries else 0
    tf_count  = sum(1 for e in entries if e.get("beat_type") == "text_frame")
    sc_count  = len(entries) - tf_count
    print(f"{len(entries)} images from {len(beats)} beats, {total_dur:.1f}s total ({total_dur / 60:.1f} min)")
    print(f"  {tf_count} text_frame (PIL), {sc_count} scene (Flux/ComfyUI)")
    print(f"Saved: {prompts_path}")


if __name__ == "__main__":
    main()
