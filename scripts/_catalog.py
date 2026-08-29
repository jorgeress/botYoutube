"""
Closed-vocabulary catalog for the structured beat format.
Single source of truth for field-to-prompt-fragment mappings.
Imported by: generate_image_prompts.py, parse_script.py, lint_script.py
"""

# ── Character anchor: auto-injected on every beat with char >= 1 ─────────────
CHARACTER_ANCHOR = (
    "stickman with round head, two small black dot eyes, "
    "simple curved line mouth, thin uniform black ink lines, "
    "no fingers, no nose"
)

# ── Style anchor: appended to every Flux prompt ──────────────────────────────
# Kept <20 words so it does not compete with content for the 4-step attention budget.
STYLE_ANCHOR = (
    "hand-drawn 2D stickman, thin black ink lines, flat color, "
    "white background, simple educational explainer style"
)

# ── Emotion -> face fragment ──────────────────────────────────────────────────
EMOTION: dict[str, str] = {
    "neutral":   "",
    "worried":   "worried expression, furrowed brows, small sweat drop beside head",
    "surprised": "wide surprised eyes, raised eyebrows, open mouth",
    "strained":  "strained frustrated expression, effort lines around the head",
    "happy":     "relaxed open posture, gentle smile",
    "curious":   "head tilted, one eyebrow raised, curious look",
    "sad":       "downturned mouth, drooping posture",
}

# ── Pose -> prompt fragment ───────────────────────────────────────────────────
POSE: dict[str, str] = {
    "standing":       "standing upright, relaxed",
    "pointing-right": "one arm extended, pointing to the right",
    "pointing-left":  "one arm extended, pointing to the left",
    "arms-crossed":   "arms crossed over the chest",
    "arms-raised":    "both arms raised upward",
    "hands-on-hips":  "hands on hips, confident stance",
    "head-in-hands":  "both hands holding the head, distressed",
    "thinking":       "one hand on chin, thoughtful",
    "holding-object": "holding the prop in both hands in front of the chest",
    "sitting-desk":   "sitting at a simple desk",
    "lying-bed":      "lying in a simple bed",
    "walking":        "walking, one foot forward",
    "running":        "running, legs mid-stride, arms bent",
    "jumping":        "jumping, both feet off the ground",
    "reaching-up":    "reaching upward with one arm",
    "kneeling":       "kneeling on the ground",
    "falling":        "falling backward, arms out",
}

# ── Pose-emotion compatibility matrix (TAREA 3) ───────────────────────────────
# Linter raises ERROR (not warning) if emotion is not in the allowed list for the pose.
# Incompatible combos produce contradictory Flux results (e.g. surprised + thinking).
_ALL_EMOTIONS = ["neutral", "worried", "surprised", "strained", "happy", "curious", "sad"]

POSE_EMOTIONS: dict[str, list[str]] = {
    "thinking":       ["neutral", "curious", "worried"],
    "head-in-hands":  ["strained", "worried", "sad"],
    "arms-raised":    ["happy", "surprised"],
    "arms-crossed":   ["worried", "neutral", "strained"],
    "walking":        ["neutral", "happy", "curious"],
    "sitting-desk":   ["neutral", "curious", "strained"],
    "reaching-up":    ["happy", "curious"],
    "running":        ["worried", "happy", "neutral"],
    "jumping":        ["happy", "surprised"],
    "standing":       _ALL_EMOTIONS,
    "pointing-right": ["neutral", "happy", "curious", "surprised"],
    "pointing-left":  ["neutral", "happy", "curious", "surprised"],
    "lying-bed":      ["neutral", "happy", "sad", "strained"],
    "hands-on-hips":  ["neutral", "happy", "curious", "strained"],
    "holding-object": ["neutral", "happy", "curious", "strained"],
    "kneeling":       ["neutral", "worried", "strained", "sad"],
    "falling":        ["worried", "surprised", "strained"],
}

# ── Background -> prompt fragment ─────────────────────────────────────────────
BG: dict[str, str] = {
    "plain-white": "plain pure white background, thin brown ground line",
    "grass-sky":   "green grass strip at the bottom, light blue sky",
    "night":       "dark blue night sky, small white dot stars, ground line",
    "dark-stars":  "pitch black sky, no sun or moon visible, faint tiny white dot stars, ground line",
    # TAREA 0 fix: was "light gray floor platform" which Flux rendered as a product-display podium
    "lab-floor":   "plain white background, light gray horizontal floor line at the bottom",
    "interior":    "simple warm room interior, thin floor line, one window",
    "prehistoric": "sandy orange-brown ground, warm earthy background",
    "space":       "deep black space, scattered small stars, a distant planet",
    "crowd":       "many tiny identical stick figures filling the background",
}

# ── Costume -> Flux prompt fragment (TAREA 1) ─────────────────────────────────
# Embedded in char value: char: 1, neutral, costume: lab-coat
# Note: "lab-coat" omits "round glasses", they distort the stickman face in test results.
COSTUME: dict[str, str] = {
    "none":          "",
    "lab-coat":      "wearing a white lab coat",
    "tie":           "wearing a simple necktie",
    "chalk-teacher": "holding a piece of chalk, simple chalkboard behind",
    "cave-person":   "messy dark hair, rough animal-skin clothing",
}

# ── Time of day -> Flux background fragment (TAREA 1) ─────────────────────────
# morning / afternoon → sprite only (sun or clock-small); no Flux fragment added.
# evening / night     → Flux bg fragment. night overrides the declared bg.
TIME_BG_FRAGMENT: dict[str, str] = {
    "morning":   "",
    "afternoon": "",
    "evening":   "window with warm amber light on the wall",
    "night":     "dark blue night background",
    "none":      "",
}

# ── Diagram symbols -> prompt fragment ───────────────────────────────────────
# Symbols with a matching sprite in assets/sprites/ are rendered by PIL (_diagram_frame.py).
# The Flux fallback fragment is used only when the sprite file is missing.
SYMBOL: dict[str, str] = {
    "question-mark": "large bold hand-drawn question mark",
    "lightbulb":     "glowing yellow lightbulb",
    "brain":         "simple hand-drawn brain outline",
    "open-book":     "open book",
    "bright-sun":    "bright yellow sun with rays",
    "cracked-sun":   "cracked yellow sun with explosion lines",
    "plant":         "small green plant",
    "dead-plant":    "drooping plant with bent stem and dry leaves, wilted and dying",
    "battery":       "battery with charge bars",
    "clock":         "simple round clock",
    "coin":          "round coin with a dollar mark",
    "globe":         "simple Earth globe",
    "skull":         "simple white skull",
    "droplet":       "single water droplet",
    "ice-crystal":   "blue ice crystal",
    "fire":          "orange flame",
    "gear":          "single mechanical gear",
    "dna-helix":     "simple DNA double helix",
    # PIL sprites: arrows, shapes, numbers
    "arrow-up":      "bold arrow pointing up",
    "arrow-down":    "bold arrow pointing down",
    "arrow-left":    "bold arrow pointing left",
    "star":          "simple five-pointed star shape, no frame, no border, isolated",
    "heart":         "red heart",
    **{f"number-{d}": f"bold number {d}" for d in range(10)},
}

# ── Prop name -> how to render it in a Flux prompt ───────────────────────────
PROP_FRAGMENT: dict[str, str] = {
    "red-X":       "large red X symbol",
    "green-check": "large green check mark",
    "star":        "yellow five-pointed star",
    "heart":       "red heart shape",
    "arrow-up":    "bold upward arrow",
    "arrow-down":  "bold downward arrow",
    "cracked-sun": "cracked yellow sun with explosion lines",
    "bright-sun":  "bright yellow sun with rays",
    "thermometer": "thermometer",
    "plant-pot":   "potted plant",
    "dead-plant":  "drooping plant with bent stem and dry leaves, wilted and dying",
    "lightbulb":   "glowing lightbulb",
    "brain":       "simple hand-drawn brain",
    "coin":        "round gold coin",
    "battery":     "battery",
    "clock":       "simple round clock",
    # "calendar" word primes Flux to generate date grids even with "no text" (inert at cfg=1.0).
    # Describe the physical shape only, without the word "calendar".
    "calendar":    "simple rectangular paper sheet with a ring binder at the top, blank white page",
    "book":        "open book",
    "beaker":      "laboratory beaker",
    "chalkboard":  "simple chalkboard",
    "phone":       "simple smartphone",
    "door":        "simple door",
    "arrow":       "bold arrow",
    "globe":       "simple Earth globe",
    "skull":       "simple skull",
    "droplet":     "water droplet",
    "ice-crystal": "blue ice crystal",
    "fire":        "orange flame",
    # TAREA 0 fix: was "mechanical gear", Flux generated 2 gears; now explicit singular
    "gear":        "single mechanical gear, one gear only",
}

# ── Prop position -> prompt fragment ──────────────────────────────────────────
PROP_POSITION: dict[str, str] = {
    "left":           "on the left side",
    "right":          "on the right side",
    "above":          "above",
    "below":          "below",
    "held":           "held in the character's hands",
    "floating-right": "floating to the right",
    "floating-left":  "floating to the left",
}

# ── Arrow -> prompt fragment ──────────────────────────────────────────────────
ARROW_DIRECTION: dict[str, str] = {
    "right": "pointing right",
    "left":  "pointing left",
    "down":  "pointing down",
    "up":    "pointing up",
}
ARROW_COLOR: dict[str, str] = {
    "red":    "bold red",
    "green":  "bold green",
    "blue":   "bold blue",
    "yellow": "bold yellow",
}

# ── Shot types ────────────────────────────────────────────────────────────────
SHOT_TYPES = frozenset({"text-frame", "diagram", "wide", "medium", "close-up"})

# ── Valid field values (used by linter) ───────────────────────────────────────
VALID_EMOTIONS  = frozenset(EMOTION.keys())
VALID_POSES     = frozenset(POSE.keys())
VALID_BGS       = frozenset(BG.keys())
VALID_SYMBOLS   = frozenset(SYMBOL.keys())
VALID_POSITIONS = frozenset(PROP_POSITION.keys())
VALID_PROPS     = frozenset(PROP_FRAGMENT.keys())
VALID_COSTUMES  = frozenset(COSTUME.keys())
VALID_TIMES     = frozenset(TIME_BG_FRAGMENT.keys())

# Fields allowed per shot type (linter enforces; parser ignores extras gracefully)
# v2 adds: props (multi-prop), time, place to all scene shots. prop (v1) kept for backward compat.
# v3 adds: desc (literal free-text scene description) to every shot, drives hosted image
#   models (Nano Banana / Gemini) that reward specificity. Optional everywhere; when absent
#   the closed-catalog assembly is used as before (backward compatible).
SHOT_ALLOWED_FIELDS: dict[str, frozenset] = {
    "text-frame": frozenset({"shot", "text", "desc"}),
    "diagram":    frozenset({"shot", "left", "right", "arrow", "bg", "labels", "desc"}),
    "wide":       frozenset({"shot", "char", "pose", "prop", "props", "time", "place", "bg", "desc"}),
    "medium":     frozenset({"shot", "char", "pose", "prop", "props", "time", "place", "bg", "desc"}),
    "close-up":   frozenset({"shot", "char", "pose", "prop", "props", "time", "place", "bg", "desc"}),
}

# ── Gemini / Nano Banana prompt scaffolding (hosted image models) ──────────────
# Used by generate_image_prompts.build_gemini_prompt() when CLIP_SOURCE == "gemini".
# These reward rich natural-language prompts, so we wrap the literal `desc:` (or a
# catalog fallback) with a fixed style preamble + anti-duplication tail rather than
# the Flux comma-soup. Keep the character description in sync with CHARACTER_ANCHOR.
# Style identity: applied to every scene beat.
GEMINI_STYLE_ID = (
    "Hand-drawn 2D cartoon, black ink on a white background, flat minimal "
    "educational-explainer style, clean and uncluttered, 16:9 aspect ratio."
)
# Character clause: chosen by char count so object-only beats never get a stray figure.
GEMINI_CHARACTER_ONE = (
    "Exactly one stickman, drawn a single time: round head, two small black dot eyes, "
    "a simple curved-line mouth, thin uniform black line weight, stick arms and legs, "
    "no fingers, no nose."
)
GEMINI_CHARACTER_TWO = (
    "Exactly two stickmen: each with a round head, two small black dot eyes, a simple "
    "curved-line mouth, thin uniform black line weight, no fingers, no nose."
)
GEMINI_NO_CHARACTER = "No people and no characters anywhere in the frame, objects only."
# Composition / caption safe zone.
GEMINI_COMPOSITION = (
    "Keep the bottom fifth of the frame clear for subtitles. Do not draw any text, "
    "letters, numbers, labels, or speech bubbles in the image."
)
# Anti-duplication: the strongest lever against Nano Banana's before/after copies.
# Generic 'nothing duplicated' is weak; this names the exact failure modes.
GEMINI_ANTI_DUP = (
    "Show one single frozen instant, never a sequence, comic strip, grid, or motion "
    "blur. Draw each object exactly once: no duplicated objects, no duplicate or extra "
    "limbs, no repeated copies of the same thing, no before-and-after versions."
)
# Framing hint per shot type.
GEMINI_SHOT_FRAMING: dict[str, str] = {
    "wide":     "Wide shot, full body and surroundings visible.",
    "medium":   "Medium shot, character from the knees up.",
    "close-up": "Close-up shot, focus tight on the key subject.",
}
