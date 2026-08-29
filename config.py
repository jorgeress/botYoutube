# ── Voice (Chatterbox TTS: local GPU, free, open-source MIT) ─────────────────
# Install: pip install chatterbox-tts torchaudio
# Voice cloning: set CHATTERBOX_REF_AUDIO to a .wav file (10-30s clean speech).
# Leave empty to use the model's default voice.
CHATTERBOX_REF_AUDIO   = ""  # empty = default voice (much faster, no cloning overhead)
CHATTERBOX_EXAGGERATION = 0.3         # 0.0 = calm/flat, 1.0 = very expressive
CHATTERBOX_CFG         = 2.0          # classifier-free guidance; 2-3 = natural calm, >5 = intense
SEGMENT_SILENCE_MS     = 500          # ms of silence between segments (topic shift)
BEAT_SILENCE_MS        = 250          # ms of silence between beats within a segment
TTS_SPEED              = 1.0          # 1.0 = no post-processing; atempo sounds robotic below 0.9

# Legacy edge-tts (kept for reference, no longer used)
TTS_VOICE  = "en-US-GuyNeural"
TTS_RATE   = "-5%"
TTS_VOLUME = "+0%"

# ── Clip source ───────────────────────────────────────────────────────────────
# "manual"     → you generate each image by hand in the AI Studio web UI (free Nano
#                Banana) and save it as clips/seg_NNN_src.png; the pipeline builds the
#                clips from them. Run `python scripts/export_prompts.py <slug>` first to
#                get a copy-paste list of all prompts + filenames.
# "gemini"     → Nano Banana (Gemini 2.5 Flash Image) hosted API, fully automated, best
#                quality + character consistency via reference image. The image API has
#                NO free tier (limit 0); requires billing enabled (~$0.039/img). Switch
#                here once billing is on.
# "comfyui"    → local GPU via ComfyUI (batches all images, model loads once)
# "huggingface"→ HF Inference API (free tier, slower, ~1000 req/month)
# "pexels"     → stock footage (requires PEXELS_API_KEY)
# "leonardo"   → requires LEONARDO_API_KEY
CLIP_SOURCE = "gemini"   # automated Nano Banana API (billing must be enabled)

# ── Gemini / Nano Banana (hosted image API) ───────────────────────────────────
# Get a free API key (no card): https://aistudio.google.com  → setx GEMINI_API_KEY "..."
# Install SDK: pip install google-genai
# gemini-2.5-flash-image = original "Nano Banana", the only variant with a usable
#   free daily quota. Pro/2 (gemini-3-pro-image-preview / gemini-3.1-flash-image-preview)
#   are higher quality but their free tier is ~3 img/day, so they cost money per video.
GEMINI_MODEL            = "gemini-2.5-flash-image"
GEMINI_REQUEST_DELAY_S  = 6.0   # throttle between calls, free tier is rate-limited per minute
GEMINI_MAX_RETRIES      = 4     # exponential backoff on 429 / transient errors
# API key: never hardcoded in this tracked file. Resolution order:
#   1) env var GEMINI_API_KEY / GOOGLE_API_KEY
#   2) secrets_local.py (gitignored: put the key there)
import os as _os
try:
    from secrets_local import GEMINI_API_KEY as _LOCAL_GEMINI_KEY
except Exception:
    _LOCAL_GEMINI_KEY = ""
GEMINI_API_KEY = (_os.environ.get("GEMINI_API_KEY", "")
                  or _os.environ.get("GOOGLE_API_KEY", "")
                  or _LOCAL_GEMINI_KEY)
# Reference image passed on every character beat to lock the recurring stickman.
# Generate one canonical "model sheet" PNG once and point here. Empty = no reference.
CHARACTER_REFERENCE_IMAGE = "assets/character_ref.png"

# ── ComfyUI local generation ──────────────────────────────────────────────────
# Start ComfyUI first: cd <your ComfyUI install> && python main.py --port 8188
# (no --highvram: model offloads between runs, prevents OOM on 8GB VRAM)
COMFYUI_URL    = "http://localhost:8188"
COMFYUI_WIDTH  = 1024                  # source image width (Ken Burns upscales to 1920)
COMFYUI_HEIGHT = 576                   # 16:9, no speed penalty vs lower res (model load dominates)
COMFYUI_STEPS  = 4                     # Schnell optimal=4, but 8 improves line detail with minimal time cost, revert to 4 if too slow
COMFYUI_BATCH_SIZE = 4                 # clips queued per batch (bounds VRAM use on 8GB)
COMFYUI_UNET   = "flux1-schnell-Q4_K_S.gguf"
COMFYUI_CLIP1  = "clip_l.safetensors"
COMFYUI_CLIP2  = "t5xxl_fp8_e4m3fn.safetensors"
COMFYUI_VAE    = "ae.safetensors"

# ── Image generation (shared by all AI sources) ───────────────────────────────
IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080

# ═══════════════════════════════════════════════════════════════════════════════
# STYLE SELECTOR: change IMAGE_STYLE_ANCHOR to switch between styles instantly
# ═══════════════════════════════════════════════════════════════════════════════

# STYLE A: White background hand-drawn stickman (based on reference images)
# Short (<20 words) so it does not compete with content for the 4-step attention budget.
# Matches _catalog.STYLE_ANCHOR: keep in sync if either is changed.
IMAGE_STYLE_A = (
    "hand-drawn 2D stickman, thin black ink lines, flat color, "
    "white background, simple educational explainer style"
)
IMAGE_ANTI_A = (
    "no photorealism, no 3D, no gradients, no textures, no shading, no dark background, "
    "no faces on back of heads, no duplicate hands, no extra limbs, "
    "no merged or fused bodies, no overlapping heads, no realistic anatomy, "
    "no random animals unless the scene explicitly includes them, "
    "no floating unrelated objects, no watermarks, no random UI elements, no subtitles bar"
)

# STYLE B: Dark background stickman (Kurzgesagt-inspired, liked in v5 tests)
# Darker muted background, bright bold character/object colors, more cinematic
IMAGE_STYLE_B = (
    "2D flat animation, stickman characters with circular heads and thin limbs, "
    "dot eyes and small curved mouth visible on all characters, faces always forward-facing, "
    "each character has exactly two hands and two feet clearly drawn, "
    "detailed scene environment in flat color blocks with dark muted background tones, "
    "bright bold accent colors for characters and key props (orange, teal, yellow, red), "
    "thick consistent black outlines on all elements, "
    "Kurzgesagt-inspired illustration quality"
)
IMAGE_ANTI_B = (
    "no gradients on characters, no textures, no photorealism, no 3D rendering, "
    "no realistic proportions, flat colors only, no white background, "
    "no faces on back of heads, no duplicate hands, no extra limbs, "
    "no merged or fused bodies, no overlapping heads, "
    "no random animals unless the scene explicitly includes them, "
    "no floating unrelated objects, no watermarks, no text overlays, no speech bubbles"
)

# ── Style palettes: PIL rendering colors per style ───────────────────────────
# Used by _text_frame.py, _overlay.py, _data_frame.py.
# Swap STYLE_PALETTE alongside IMAGE_STYLE_ANCHOR to keep PIL consistent with Flux.
STYLE_PALETTE_A = {
    # text_frame / data_frame background canvas
    "frame_bg":          (255, 255, 255),   # white
    "frame_fg":          (12,  12,  12),    # near-black text
    "frame_shadow":      (215, 215, 215),   # light gray drop-shadow
    "frame_accent":      (200, 28,  28),    # red dashed underline
    # stat / number overlays drawn on top of Flux images
    "stat_fill":         (10,  10,  10),
    "stat_outline":      (255, 255, 255),
    # label pill (short text tag drawn on Flux image)
    "label_bg":          (255, 255, 255),
    "label_fg":          (10,  10,  10),
    "label_border":      (180, 180, 180),
    # timeline
    "timeline_bar":      (40,  40,  40),
    "timeline_pin":      (200, 40,  40),
    "timeline_label_fg": (180, 20,  20),
    "timeline_outline":  (255, 255, 255),
    # bar chart text
    "chart_label":       (30,  30,  30),
    "chart_title":       (30,  30,  30),
}
STYLE_PALETTE_B = {
    "frame_bg":          (18,  18,  32),    # dark navy canvas
    "frame_fg":          (245, 245, 245),   # near-white text
    "frame_shadow":      (50,  50,  70),    # dark tinted drop-shadow
    "frame_accent":      (255, 150,   0),   # orange accent (Kurzgesagt-ish)
    "stat_fill":         (245, 245, 245),
    "stat_outline":      (20,  20,  40),
    "label_bg":          (30,  30,  55),
    "label_fg":          (245, 245, 245),
    "label_border":      (90,  90, 140),
    "timeline_bar":      (180, 180, 200),
    "timeline_pin":      (255, 150,   0),
    "timeline_label_fg": (255, 200,  50),
    "timeline_outline":  (18,  18,  32),
    "chart_label":       (220, 220, 230),
    "chart_title":       (245, 245, 245),
}

# ── Font search paths: handwriting fonts first (install from Google Fonts) ───
# Priority: Caveat > Architects Daughter > Patrick Hand > system fallbacks.
# Download TTF from fonts.google.com and copy to C:/Windows/Fonts/ to activate.
# If none are installed, falls back to Impact/Arial automatically, no code change needed.
_USER_FONTS = "C:/Users/jorge/AppData/Local/Microsoft/Windows/Fonts"
FONT_PATHS_BOLD = [
    # User fonts directory (no admin needed, installed via Windows font manager)
    f"{_USER_FONTS}/Caveat-Bold.ttf",
    f"{_USER_FONTS}/CaveatBrush-Regular.ttf",
    f"{_USER_FONTS}/ArchitectsDaughter-Regular.ttf",
    f"{_USER_FONTS}/PatrickHand-Regular.ttf",
    # System fonts fallback
    "C:/Windows/Fonts/Caveat-Bold.ttf",
    "C:/Windows/Fonts/CaveatBrush-Regular.ttf",
    "C:/Windows/Fonts/ArchitectsDaughter-Regular.ttf",
    "C:/Windows/Fonts/PatrickHand-Regular.ttf",
    "C:/Windows/Fonts/impact.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
FONT_PATHS_REGULAR = [
    f"{_USER_FONTS}/Caveat-Regular.ttf",
    f"{_USER_FONTS}/CaveatBrush-Regular.ttf",
    f"{_USER_FONTS}/ArchitectsDaughter-Regular.ttf",
    f"{_USER_FONTS}/PatrickHand-Regular.ttf",
    "C:/Windows/Fonts/Caveat-Regular.ttf",
    "C:/Windows/Fonts/CaveatBrush-Regular.ttf",
    "C:/Windows/Fonts/ArchitectsDaughter-Regular.ttf",
    "C:/Windows/Fonts/PatrickHand-Regular.ttf",
    "C:/Windows/Fonts/calibri.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/verdana.ttf",
]

# ── Active style: change all four lines together when switching ──────────────
# Style A: white background hand-drawn stickman (currently active)
# Style B: dark background Kurzgesagt-inspired
ACTIVE_STYLE       = "A"            # "A" or "B"
IMAGE_STYLE_ANCHOR = IMAGE_STYLE_A
IMAGE_ANTI_QUALITY = IMAGE_ANTI_A
STYLE_PALETTE      = STYLE_PALETTE_A

# Combined prefix used by generate_image_prompts.py
IMAGE_STYLE_PREFIX = f"{IMAGE_STYLE_ANCHOR}, {{scene}}, {IMAGE_ANTI_QUALITY}"

# ── Hugging Face Inference API ────────────────────────────────────────────────
# Free tier: ~1000 req/month, email signup only, no credit card.
# Token: huggingface.co → Settings → Access Tokens → New token (Read)
HUGGINGFACE_TOKEN= ""  # set via HF_TOKEN env var or paste your token here (not committed)
HF_MODEL = "black-forest-labs/FLUX.1-schnell"  # fast, high quality, free tier
HF_WIDTH = 1024
HF_HEIGHT = 576                        # 16:9 at 1024px; Ken Burns upscales to 1920x1080

# ── Pollinations.ai (disabled: free tier IP-rate-limited) ───────────────────
POLLINATIONS_WIDTH = 1280
POLLINATIONS_HEIGHT = 720
POLLINATIONS_MODEL = ""

# ── Leonardo.ai (fallback, requires LEONARDO_API_KEY) ────────────────────────
LEONARDO_MODEL_ID = "aa77f04e-3eec-4034-9c07-d0f619684628"

# ── Pexels ────────────────────────────────────────────────────────────────────
PEXELS_VIDEO_ORIENTATION = "landscape"
PEXELS_VIDEO_MIN_DURATION = 5

# ── Ken Burns (FFmpeg) ────────────────────────────────────────────────────────
KEN_BURNS_FPS = 25
# Image changes are driven by the (visual) beats written in the script, one
# image per beat. A safety auto-split kicks in for any beat longer than this,
# so a single image never lingers too long even if the writer wrote a long beat.
BEAT_MAX_IMAGE_DURATION_S = 6

# ── Image prompt chunks (from SRT) ───────────────────────────────────────────
CHUNK_MIN_DURATION_S = 6
CHUNK_MAX_DURATION_S = 10

# ── Audio post-processing ────────────────────────────────────────────────────
# Applied to narration.mp3 after merge, before assembly.
# Set False to skip in debug / when re-running assembly only.
AUDIO_POSTPROCESS = True

# ── Background music ─────────────────────────────────────────────────────────
# Leave empty to skip mixing. Drop tracks into assets/music/ and point here.
BACKGROUND_MUSIC_PATH = ""   # e.g. "assets/music/lofi_focus.mp3"
BACKGROUND_MUSIC_DB   = -20  # dB relative to narration (-20 = very subtle)

# ── Subtitles ─────────────────────────────────────────────────────────────────
BURN_SUBTITLES  = True   # False = generate .srt/.ass but skip burning into video
UPLOAD_SRT      = True   # reminder: upload subtitles.srt to YouTube Studio manually

SUBTITLE_STYLE = {
    "font":          "Montserrat ExtraBold",  # fallback: "Arial Bold"
    "font_size":     52,
    "color_base":    "&H00FFFFFF",             # white
    "color_active":  "&H0000FFFF",             # yellow (BGR in .ass: 00FFFF = yellow)
    "outline_color": "&H00000000",             # black outline
    "outline_width": 3,
    "position_y":    960,                      # ~89% of 1080, standard subtitle position
    "max_words":     5,                        # words per visible group
}

# ── Assembly ──────────────────────────────────────────────────────────────────
ASSEMBLE_WITH_FFMPEG = True

# ── Paths ─────────────────────────────────────────────────────────────────────
INPUT_SCRIPT = "input/script.txt"
OUTPUT_DIR = "output"
