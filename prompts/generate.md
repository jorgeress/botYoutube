# Generar un guion

Plantilla de prompt para escribir un guion entero. Sustituye `{tema}` por el
tema del video y pasale todo esto al modelo con el que escribas.

Generate a complete faceless YouTube script for the following topic: {tema}

## Instructions

1. Read `prompts/script_template.md` in full, it is the single source of truth for the
   structured beat format, the closed catalogs (shot/char/pose/prop/bg/diagram/text), the
   color palette, and the 8 rules. Read `prompts/beat_format.md` for the exact field reference.

2. Generate a full production-length script (~8 minutes) optimized for maximum retention:
   - **85-105 beats total**: each beat = one `(fields)` line + one narration sentence.
   - **6-8 segments** of 12-16 beats each, distinct `bg:` per segment.
   - Narration word count **950-1150** (~125 wpm = ~8 min).
   - **Language: English** for both narration and every `text:` value.
   - **Retention arc** (from template RETENTION ARCHITECTURE section):
     - Beat 1: starts with "You", viewer is inside the scene, not watching from outside.
     - Segment 1: hook + counterintuitive premise + promise (beats 1-5).
     - Segment 2: root cause / science (beats 6-20), ends with curiosity pull.
     - Segment 3: mechanism + counterintuitive twist + cycle diagram (beats 21-40).
     - Segment 4: stakes / cost of not knowing (beats 41-55).
     - Segment 5: named solution technique + text-frame + diagram (beats 56-75).
     - Segment 6: payoff + identity reframe + strong closing beat (beats 76-90+).
     - Every segment except the last ends with a pull line ("But here is the part nobody explains...").
     - Pattern interrupt every 8-12 beats (bg change, diagram, text-frame, emotion shift).

3. Every beat uses **closed-catalog fields PLUS a literal `desc:`**. Pick the catalog
   values exclusively from the template lists; write `desc:` as plain literal English:
   - `shot:` ∈ {text-frame, diagram, wide, medium, close-up}
   - `desc:` **on every beat**: one concrete clause (~12-25 words) of exactly what is in
     the frame. Describe the **finished static state, never the action**: Nano Banana is
     literal and additive, so transition verbs (snapping, falling, sliding off, splitting,
     peeling, lifting away, shedding) make it duplicate the object. Write the end position
     instead, count objects explicitly, and place any detached part as its own single object
     in a definite spot. Example: not "the handle snaps off and falls" but "a handle-less mug
     in his hand, one detached handle resting on the floor below". This field is what makes
     the image actually match the sentence without duplicates.
   - `char:` count ∈ {0,1,2}; emotion ∈ {neutral, worried, surprised, strained, happy, curious, sad}
   - `pose:` from the pose catalog (only when char ≥ 1); any emotion pairing is fine
   - `prop:` optional catalog prop (the real objects go in `desc:`); `props:` max two
   - `bg:` from the background catalog
   - `text:` only on `shot: text-frame`, UPPERCASE, ≤4 words, ≤15 chars/word, ASCII only
   - `left:`/`right:` symbols + explicit `arrow:` + optional `labels:` on diagrams
   - **Schema v2 fields** (add when narration triggers them):
     - `time: morning/afternoon/evening/night`, when narration mentions time of day
     - `place: 'MIT'`: when narration names a specific institution or city
     - `costume: lab-coat/tie/chalk-teacher/cave-person`, for character roles
     - `props: item1 pos, item2 pos`, only when genuinely need two props

4. Enforce the hard rules while writing:
   - **One clear moment per beat.** The scene lives in `desc:` (one main subject + at most
     2-3 related objects). `pose:`/`prop:` are secondary hints, not hard limits.
   - **One text element per beat**, only in text-frame beats.
   - **Max one text-frame every 8-10 beats.**
   - **Continuity:** all beats in a segment share the same `bg:` unless the location changes.
   - **Emotion matches narration tone.** Any pose+emotion pairing is fine with Nano Banana;
     the matrix in the template is just a hint for natural pairings.
   - **Diagrams read left→right** (cause left, effect right, explicit arrow).
   - **No blacklisted words** (realistic, detailed, photo, 3D, person, man, woman, human).
   - Never describe the character's appearance, the CHARACTER ANCHOR is auto-injected.
   - **Sync rule:** add `time:`/`place:`/`costume:` only when narration explicitly triggers them.
   - **NEVER use em-dashes (`: `) or double dashes (`--`) in narration.** Use a comma or period
     instead. They appear as `, ` in subtitles and are read incorrectly by TTS.
   - **Text-frame narration must say the concept word.** When `shot: text-frame | text: 'WORD'`,
     the narration MUST say that exact word. `(text: 'PROCRASTINATION')` → "Scientists call it
     procrastination..." never just allude to it without naming it.

5. Before finishing, run the template's self-check on the first 10 beats, fix failures,
   then scan the rest for the same issues.

## Output

1. Write the complete script to `input/script.txt` (overwrite existing content).
2. Count the beats and estimate duration (beats × ~4s).
3. Generate a URL-friendly ASCII slug from the title (lowercase, hyphens, max 50 chars, no articles).
4. Print:

```
Script written to input/script.txt
Beats: XX | Estimated duration: ~X min XX sec
Slug: your-slug-here

To run the pipeline:
  python run_pipeline.py your-slug-here
```

Do NOT run the pipeline yourself, only generate and save the script.
