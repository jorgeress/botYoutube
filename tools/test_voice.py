"""
Quick voice clone test: generates 3 TTS samples with the reference audio.
Output: tools/voice_test_*.mp3
Run: python tools/test_voice.py
"""
import os, sys, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import CHATTERBOX_REF_AUDIO, CHATTERBOX_EXAGGERATION, CHATTERBOX_CFG

SENTENCES = [
    "Every habit you have today was once a choice you made.",
    "Your brain doesn't finish learning when you study, it finishes while you sleep.",
    "Scientists call this the status quo bias, and it affects every decision you make.",
]

def main():
    if not CHATTERBOX_REF_AUDIO or not os.path.exists(CHATTERBOX_REF_AUDIO):
        print(f"ERROR: reference audio not found: {CHATTERBOX_REF_AUDIO}")
        sys.exit(1)

    import torch, torchaudio as ta
    from chatterbox.tts import ChatterboxTTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Chatterbox on {device.upper()}...")
    model = ChatterboxTTS.from_pretrained(device=device)
    print(f"Voice ref: {CHATTERBOX_REF_AUDIO}\n")

    out_dir = os.path.dirname(os.path.abspath(__file__))
    for i, sentence in enumerate(SENTENCES):
        wav_path = os.path.join(out_dir, f"voice_test_{i+1}.wav")
        mp3_path = os.path.join(out_dir, f"voice_test_{i+1}.mp3")
        print(f"[{i+1}/3] {sentence[:60]}...")
        wav = model.generate(
            sentence,
            audio_prompt_path=CHATTERBOX_REF_AUDIO,
            exaggeration=CHATTERBOX_EXAGGERATION,
            cfg_weight=CHATTERBOX_CFG,
        )
        ta.save(wav_path, wav, model.sr)
        subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", mp3_path],
            check=True, capture_output=True,
        )
        os.remove(wav_path)
        size_kb = os.path.getsize(mp3_path) // 1024
        print(f"   -> {mp3_path} ({size_kb}KB)")

    print(f"\nDone. Play tools/voice_test_1.mp3 through voice_test_3.mp3 to evaluate.")
    print("If the timbre sounds wrong, try a different 25s segment:")
    print("  ffmpeg -y -i assets/voice/<file>.mp3 -ss <START> -t 25 -ar 44100 -ac 1 assets/voice/reference.wav")

if __name__ == "__main__":
    main()
