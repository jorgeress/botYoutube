import torch
from diffusers import StableDiffusionPipeline

MODEL_PATH = "tools/lora_training/sd15_diffusers"
LORA_PATH = "tools/lora_training/output/pytorch_lora_weights.safetensors"
OUTPUT_PATH = "tools/lora_training/test_output.png"

PROMPT = "mspaint style, 2D simple animation, stick figure with round white head, flat colors, thick black outlines, a person walking on the street, YouTube explainer video style, hand-drawn wobble lines, no gradients"
NEGATIVE_PROMPT = "realistic, photorealistic, 3d, detailed, high quality, blurry, smooth shading, gradients, complex background, render, CGI"

pipe = StableDiffusionPipeline.from_pretrained(MODEL_PATH, torch_dtype=torch.float16)
pipe.load_lora_weights(LORA_PATH)
pipe = pipe.to("cuda")

image = pipe(
    prompt=PROMPT,
    negative_prompt=NEGATIVE_PROMPT,
    num_inference_steps=30,
    guidance_scale=7.5,
    lora_scale=0.9,
).images[0]

image.save(OUTPUT_PATH)
print(f"Imagen guardada en: {OUTPUT_PATH}")
