import torch
from diffusers import StableDiffusionPipeline
from PIL import Image

MODEL_PATH = "tools/lora_training/sd15_diffusers"
LORA_PATH = "tools/lora_training/output/pytorch_lora_weights.safetensors"
OUTPUT_DIR = "tools/lora_training/"

NEGATIVE = "realistic, photorealistic, 3d, detailed, high quality, blurry, smooth shading, gradients, complex background, render, CGI"

STYLE = "mspaint style, 2D simple animation, flat colors, thick black outlines, hand-drawn wobble lines, no gradients, YouTube explainer video style"

TESTS = [
    # Comparativa de scale con nuevo estilo
    ("scale_0.5",    f"{STYLE}, a cat sitting, white background",              0.5),
    ("scale_0.7",    f"{STYLE}, a cat sitting, white background",              0.7),
    ("scale_0.9",    f"{STYLE}, a cat sitting, white background",              0.9),
    ("scale_1.1",    f"{STYLE}, a cat sitting, white background",              1.1),
    # Escenas del dataset real
    ("stickfigure",  f"{STYLE}, stick figure person with round white head, standing",  0.9),
    ("desk_scene",   f"{STYLE}, stick figure sitting at a desk with a computer",       0.9),
    ("outdoor",      f"{STYLE}, two stick figures outdoors, simple sky background",    0.9),
    ("animal",       f"{STYLE}, simple cartoon monkey, white background",              0.9),
    # Sin trigger word (baseline)
    ("no_trigger",   "2D simple animation, flat colors, thick black outlines, a cat sitting", 0.9),
]

pipe = StableDiffusionPipeline.from_pretrained(MODEL_PATH, torch_dtype=torch.float16)
pipe.load_lora_weights(LORA_PATH)
pipe = pipe.to("cuda")

for name, prompt, scale in TESTS:
    print(f"Generando: {name} | scale={scale} | prompt={prompt}")
    image = pipe(
        prompt=prompt,
        negative_prompt=NEGATIVE,
        num_inference_steps=30,
        guidance_scale=7.5,
        lora_scale=scale,
    ).images[0]
    path = f"{OUTPUT_DIR}test_{name}.png"
    image.save(path)
    print(f"  -> {path}")

print("Listo. Revisa tools/lora_training/test_*.png")
