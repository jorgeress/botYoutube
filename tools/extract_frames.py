"""
Descarga videos de YouTube y extrae frames para dataset de LoRA.

Uso:
    python tools/extract_frames.py <URL_o_playlist>
    python tools/extract_frames.py https://youtube.com/watch?v=xxxx
    python tools/extract_frames.py https://youtube.com/@tucanalURL

Opciones:
    --fps 0.2        frames por segundo (0.2 = 1 cada 5s, default)
    --fps 0.5        1 frame cada 2s (para videos con cambios rapidos)
    --no-download    solo extraer frames de videos ya descargados en raw_frames/videos/

Resultado:
    tools/lora_training/raw_frames/   <- todos los frames extraidos
    (luego copias los buenos a tools/lora_training/selected/)
"""

import argparse
import os
import subprocess
import sys


VIDEOS_DIR  = "tools/lora_training/raw_frames/videos"
FRAMES_DIR  = "tools/lora_training/raw_frames"


def download_video(url: str, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--format", "bestvideo[height<=1080][ext=mp4]/bestvideo[height<=1080]/best[height<=1080]",
        "--output", os.path.join(out_dir, "%(title).60s__%(id)s.%(ext)s"),
        "--no-playlist" if "watch?v=" in url else "--yes-playlist",
        "--ignore-errors",
        url,
    ]
    print(f"Descargando: {url}")
    subprocess.run(cmd, check=True)
    return [
        os.path.join(out_dir, f)
        for f in os.listdir(out_dir)
        if f.endswith((".mp4", ".mkv", ".webm"))
    ]


def extract_frames(video_path: str, frames_dir: str, fps: float) -> int:
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    out_dir = os.path.join(frames_dir, video_name)
    os.makedirs(out_dir, exist_ok=True)

    out_pattern = os.path.join(out_dir, "frame_%05d.jpg")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"fps={fps},scale=512:512:force_original_aspect_ratio=increase,crop=512:512",
        "-q:v", "2",
        out_pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR ffmpeg: {result.stderr[-200:]}")
        return 0

    count = len([f for f in os.listdir(out_dir) if f.endswith(".jpg")])
    print(f"  {count} frames -> {out_dir}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Extrae frames de YouTube para dataset LoRA")
    parser.add_argument("url", nargs="?", help="URL del video o canal")
    parser.add_argument("--fps", type=float, default=0.2,
                        help="Frames por segundo a extraer (0.2 = 1 cada 5s, default)")
    parser.add_argument("--no-download", action="store_true",
                        help="Saltarse la descarga, procesar videos ya en raw_frames/videos/")
    args = parser.parse_args()

    if args.no_download:
        if not os.path.exists(VIDEOS_DIR):
            print(f"ERROR: {VIDEOS_DIR} no existe.")
            sys.exit(1)
        videos = [
            os.path.join(VIDEOS_DIR, f)
            for f in os.listdir(VIDEOS_DIR)
            if f.endswith((".mp4", ".mkv", ".webm"))
        ]
        if not videos:
            print(f"No hay videos en {VIDEOS_DIR}")
            sys.exit(1)
    else:
        if not args.url:
            print("ERROR: Proporciona una URL. Uso: python tools/extract_frames.py <URL>")
            sys.exit(1)
        videos = download_video(args.url, VIDEOS_DIR)

    if not videos:
        print("No se encontraron videos para procesar.")
        sys.exit(1)

    total_frames = 0
    for video in videos:
        print(f"\nExtrayendo frames de: {os.path.basename(video)}")
        total_frames += extract_frames(video, FRAMES_DIR, args.fps)

    print(f"\n{'='*50}")
    print(f"Total frames extraidos: {total_frames}")
    print(f"Ubicacion: {FRAMES_DIR}")
    print(f"\nSiguiente paso:")
    print(f"  Revisa las imagenes y copia las mejores 50-100 a:")
    print(f"  tools/lora_training/selected/")
    print(f"  Luego ejecuta: python tools/prepare_dataset.py")
