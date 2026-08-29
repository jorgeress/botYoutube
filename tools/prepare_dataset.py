"""
Prepara el dataset para entrenar el LoRA.

Lee las imagenes de tools/lora_training/selected/
Las redimensiona a 512x512 y genera captions para cada una.

El caption sigue el patron:
    mspaint style, [descripcion], stick figure drawing

Uso:
    python tools/prepare_dataset.py
    python tools/prepare_dataset.py --trigger mspaint_style
    python tools/prepare_dataset.py --caption-only  (si ya tienes las imagenes preparadas)

Resultado en tools/lora_training/dataset/
    imagen_001.jpg  + imagen_001.txt  (caption)
    imagen_002.jpg  + imagen_002.txt
    ...
"""

import argparse
import os
import shutil
import subprocess
import sys


SELECTED_DIR = "tools/lora_training/selected"
DATASET_DIR  = "tools/lora_training/dataset"
TRIGGER_WORD = "mspaint style"


def resize_image(src: str, dst: str) -> bool:
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-vf", "scale=512:512:force_original_aspect_ratio=increase,crop=512:512,format=rgb24",
        "-q:v", "2", dst,
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def write_caption(image_path: str, trigger: str) -> None:
    base = os.path.splitext(image_path)[0]
    caption_path = base + ".txt"
    if os.path.exists(caption_path):
        return
    caption = (
        f"{trigger}, stick figure drawing, ms paint amateur art, "
        "thick black outlines, white background, flat colors, "
        "simple shapes, childish drawing style"
    )
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default=TRIGGER_WORD,
                        help=f"Trigger word para el LoRA (default: '{TRIGGER_WORD}')")
    parser.add_argument("--caption-only", action="store_true",
                        help="Solo generar captions, no copiar/redimensionar imagenes")
    args = parser.parse_args()

    os.makedirs(DATASET_DIR, exist_ok=True)

    images = [
        f for f in os.listdir(SELECTED_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
    ]

    if not images:
        print(f"ERROR: No hay imagenes en {SELECTED_DIR}")
        print(f"  Copia tus mejores frames ahi primero.")
        sys.exit(1)

    print(f"Preparando {len(images)} imagenes con trigger word: '{args.trigger}'")

    ok = 0
    for i, fname in enumerate(sorted(images), 1):
        src = os.path.join(SELECTED_DIR, fname)
        dst = os.path.join(DATASET_DIR, f"img_{i:04d}.jpg")

        if not args.caption_only:
            if resize_image(src, dst):
                ok += 1
            else:
                print(f"  WARN: no se pudo procesar {fname}")
                continue
        else:
            dst = os.path.join(DATASET_DIR, fname)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
            ok += 1

        write_caption(dst, args.trigger)

    print(f"\n{ok}/{len(images)} imagenes preparadas en {DATASET_DIR}")
    print(f"\nSiguiente paso: entrenar el LoRA con kohya_ss")
    print(f"  Trigger word para usar en prompts: '{args.trigger}'")
    print(f"  Pon el .safetensors resultante en: C:/dev/ComfyUI/models/loras/")


if __name__ == "__main__":
    main()
