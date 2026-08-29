# Structured Beat Format: Canonical Spec

Single source of truth for the structured beat format. Read by:
- `prompts/script_template.md`: teaches the model to produce this format
- `scripts/parse_script.py`: parses fields, dispatches on `shot:`
- `scripts/generate_image_prompts.py`: `enrich_visual()` maps each field value to a fixed fragment
- `scripts/lint_script.py`: validates every field against the closed vocabularies

**Why structured:** `Flux Schnell Q4 + 4 steps + cfg=1.0` attends to only ~3-4
prompt elements and ignores the negative prompt. The only way to get few errors is
to feed it exactly the 3-4 things it draws well, phrased the exact way that works.
Closed vocabularies = the model selects, never invents → deterministic, testable, repeatable.

---

## Syntax

One beat = one parenthesized line of `key: value` pairs separated by `|`, followed by
the narration sentence below it.

```
(shot: medium | char: 1, worried | pose: arms-crossed | prop: red-X right | bg: plain-white)
Every time you try to change, your brain treats it like a threat.
```

- Keys are lowercase, fixed. Values come from the closed catalogs below.
- A field is omitted when not used (e.g. a diagram has no `pose:`).
- Multi-word values are hyphenated: `red-X`, `cracked-sun`, `lab-floor`, `open-book`.
- The parser splits on `|`, then on the first `:`. `char:` value may contain a comma.

---

## Shot types: dispatch + allowed fields

`shot:` is required and decides the render path and which other fields are valid.

| `shot:` | Render path | Allowed fields | Use for |
|---|---|---|---|
| `text-frame` | **PIL only** (no Flux) | `text:` | concept name reveal, key stat, section title |
| `diagram` | Flux, **no character** | `left:` `right:` `arrow:` `bg:` | cause→effect, before→after, A leads to B |
| `wide` | Flux | `char:` `pose:` `prop:` `bg:` | establishing scene, full body, environment |
| `medium` | Flux | `char:` `pose:` `prop:` `bg:` | default, character waist-up with one prop |
| `close-up` | Flux | `char:` `pose:` `prop:` `bg:` | hands, a single object, an emotional face |

**Element budget (hard rule):** a scene beat carries at most **4 content elements**,
`char(+emotion)` + `pose` + **one** `prop` + `bg`. Exactly **one** prop per beat. If a
beat needs two props, split it into two beats or make it a `diagram`. This budget is
the format's main defense against the 4-step attention ceiling.

---

## `char:` count + emotion

`char: <count>[, <emotion>]`

- **count:** `0`, `1`, or `2`. Never more, Flux Schnell cannot do crowds; a crowd is a
  `bg:` choice (`crowd`), not many characters.
- **emotion** (closed catalog → face fragment):

| value | prompt fragment |
|---|---|
| `neutral` | *(none)* |
| `worried` | worried expression, furrowed brows, small sweat drop beside head |
| `surprised` | wide surprised eyes, raised eyebrows, open mouth |
| `strained` | strained frustrated expression, effort lines around the head |
| `happy` | relaxed open posture, gentle smile |
| `curious` | head tilted, one eyebrow raised, curious look |
| `sad` | downturned mouth, drooping posture |

**CHARACTER ANCHOR (auto-injected by the pipeline on every beat with `char ≥ 1`,
never written in the script):**
> `stickman with round head, two small black dot eyes, simple curved line mouth, thin uniform black ink lines, no fingers, no nose`

This is the single biggest fix for cross-frame consistency. The model never describes the
character's appearance: only count + emotion + pose.

---

## `pose:` closed catalog (only when `char ≥ 1`)

Flux Schnell destroys complex poses. Pick one; never invent.

| value | prompt fragment |
|---|---|
| `standing` | standing upright, relaxed |
| `pointing-right` | one arm extended, pointing to the right |
| `pointing-left` | one arm extended, pointing to the left |
| `arms-crossed` | arms crossed over the chest |
| `arms-raised` | both arms raised upward |
| `hands-on-hips` | hands on hips, confident stance |
| `head-in-hands` | both hands holding the head, distressed |
| `thinking` | one hand on chin, thoughtful |
| `holding-object` | holding the prop in both hands in front of the chest |
| `sitting-desk` | sitting at a simple desk |
| `lying-bed` | lying in a simple bed |
| `walking` | walking, one foot forward |
| `running` | running, legs mid-stride, arms bent |
| `jumping` | jumping, both feet off the ground |
| `reaching-up` | reaching upward with one arm |
| `kneeling` | kneeling on the ground |
| `falling` | falling backward, arms out |

---

## `prop:` one symbol/object + optional position

`prop: <name> [position]`: exactly one per beat.

**Position** (closed): `left` `right` `above` `below` `held` `floating-right` `floating-left`.
Default when omitted: `beside the character`.

**Common prop names** (hyphenated; extend the catalog as new validated props appear):
`red-X` · `green-check` · `cracked-sun` · `bright-sun` · `thermometer` · `plant-pot` ·
`dead-plant` · `lightbulb` · `brain` · `coin` · `battery` · `clock` · `calendar` ·
`book` · `beaker` · `chalkboard` · `phone` · `door` · `arrow` · `globe` · `skull` ·
`droplet` · `ice-crystal` · `fire` · `gear`.

Colors follow the palette (below): `red-X` = danger, `green-check` = positive, etc.

---

## `text:` the one text element (PIL-rendered)

Used **only on `shot: text-frame`** (rendered full-frame by `_text_frame.py`). In-scene
labels burned by Flux are forbidden (lottery at 4 steps); scene text waits for the
PIL-overlay + VLM-grounding path (see `IMPROVEMENT_PLAN.md` §C).

`text: 'EXACT WORDS'`

**Hard rules (the linter enforces):**
- **ALWAYS UPPERCASE**: Flux/PIL spell uppercase far better.
- **≤ 4 words AND ≤ 15 characters per word.** `NEUROPLASTICITY` (15) is the limit.
- **ASCII only:** A-Z, 0-9, `%`, space. **No** apostrophes, `&`, accents, or other punctuation.
- Lift the words **directly from the narration**, the exact concept name or stat,
  never a paraphrase or motivational phrase.

---

## `diagram` fields: `left:` `right:` `arrow:`

For cause→effect / before→after. **No character.** Reading direction is fixed:
**cause/before on the LEFT, effect/after on the RIGHT.**

- `left:` and `right:` take a **symbol** from the catalog below.
- `arrow:` = `<direction> [color]`, direction in `right left down up` (default `right`),
  color from the palette (default `red`). Always explicit, Flux draws ambiguous or
  bidirectional arrows otherwise.

**Symbol catalog** (for `left:`/`right:` and floating symbols):

| value | fragment | value | fragment |
|---|---|---|---|
| `question-mark` | large bold hand-drawn question mark | `clock` | simple round clock |
| `lightbulb` | glowing yellow lightbulb | `coin` | round coin with a dollar mark |
| `brain` | simple hand-drawn brain outline | `globe` | simple Earth globe |
| `open-book` | open book | `skull` | simple white skull |
| `bright-sun` | bright yellow sun with rays | `droplet` | single water droplet |
| `cracked-sun` | cracked yellow sun with explosion lines | `ice-crystal` | blue ice crystal |
| `plant` | small green plant | `fire` | orange flame |
| `dead-plant` | wilting brown plant | `gear` | single mechanical gear |
| `battery` | battery with charge bars | `dna-helix` | simple DNA double helix |

---

## `bg:` closed background catalog

| value | prompt fragment |
|---|---|
| `plain-white` | plain pure white background, thin brown ground line |
| `grass-sky` | green grass strip at the bottom, light blue sky |
| `night` | dark blue night sky, small white dot stars, ground line |
| `dark-stars` | pitch black sky, no sun or moon visible, faint tiny white dot stars, ground line |
| `lab-floor` | plain white background, light gray floor platform |
| `interior` | simple warm room interior, thin floor line, one window |
| `prehistoric` | sandy orange-brown ground, warm earthy background |
| `space` | deep black space, scattered small stars, a distant planet |
| `crowd` | many tiny identical stick figures filling the background |

**Continuity rule:** all beats in the same `[SEGMENT N]` use the **same `bg:`** unless the
narration explicitly changes location. This stops arbitrary visual jumps between beats.

---

## Color palette: fixed function, forbid the rest

Only these four saturated colors, each with a fixed meaning. Everything else is black ink
on white. This gives channel identity and stops Flux from inventing random gradients.

| Color | Function |
|---|---|
| **red** | danger, cost, stop, death, heat |
| **green** | energy, positive, life, growth |
| **blue** | science, brain, water, cold |
| **yellow** | idea, sun, energy source |

---

## Style anchor (config, applied by the pipeline)

Kept **short (< 20 words)** so it doesn't compete with the content for the model's
attention: `hand-drawn 2D stickman, thin black ink lines, flat color, white background,
simple educational explainer style`. The long "no extra hands / no merged bodies" guardrail
list is dropped: it is inert at `cfg=1.0` and only burned attention.

---

## Blacklist: never appears in any field value

No native negative prompt exists, so wording is the only defense. These words push Flux
toward photorealism and must never be used: `realistic`, `detailed`, `photo`,
`photograph`, `3D`, `render`, `person`, `man`, `woman`, `human` (always `stickman`),
plus complex emotion names without a visual descriptor (use the `emotion:` catalog).

---

## Seed strategy (pipeline)

Seed is derived from `segment_id` so consecutive beats in a segment share style, with a
small per-beat offset for composition variety:
`base = sha256(out_dir:segment_id); seed = base + beat_index_within_segment`.
`--force` re-rolls. (Current code seeds per global index, change in implementation.)

---

## Text-frame frequency

Max **1 `text-frame` every 8-10 beats**. They work well but become monotonous if overused.

---

## Validation (lint_script.py)

A beat is valid when:
- `shot:` ∈ {text-frame, diagram, wide, medium, close-up}
- only the fields allowed for that shot are present
- `char` count ∈ {0,1,2}; `emotion` ∈ catalog; `pose` ∈ catalog (and present only if char≥1)
- exactly one `prop:` on scene beats; `prop` position ∈ catalog
- `bg:` ∈ catalog
- `text:` UPPERCASE, ≤4 words, ≤15 chars/word, ASCII-only, only on `text-frame`
- `left`/`right` symbols ∈ catalog; `arrow` direction ∈ catalog
- text-frame frequency ≤ 1 per 8 beats
- all beats in a segment share `bg:` unless narration changes location

---

## Backward compatibility

The old free-prose `(visual ...)` format still parses (a beat with no `shot:` key is
treated as legacy prose and routed through the old `enrich_visual()` path). New scripts
use the structured format. Detection: a beat is structured iff its first field key is `shot:`.

---

## Example beats

```
(shot: text-frame | text: 'EGO DEPLETION')
There is a name for this. Scientists call it ego depletion.

(shot: medium | char: 1, worried | pose: arms-crossed | prop: red-X right | bg: plain-white)
Every time you try to change, your brain treats it like a threat.

(shot: diagram | left: question-mark | right: lightbulb | arrow: right yellow | bg: plain-white)
A simple question is what turns into a real discovery.

(shot: wide | char: 1, happy | pose: standing | prop: bright-sun above | bg: grass-sky)
For now, everything feels perfectly normal under the bright sun.

(shot: close-up | char: 0 | prop: thermometer | bg: dark-stars)
Without the sun, the temperature begins to collapse.
```
