"""Generate Vietnamese offline audio clips via VieNeu TTS API.

Calls POST /synthesize on VieNeu-TTS server, converts PCM16 to OGG,
and saves to audio/offline/ directory.

Usage:
    python scripts/generate-offline-audio-clips.py [--url http://localhost:5001]

Requirements:
    pip install requests soundfile numpy
"""

import argparse
import os
import struct
import sys

import numpy as np
import requests
import soundfile as sf

# Offline clips: (filename, Vietnamese text)
CLIPS = [
    ("offline-sleepy.ogg", "Mình buồn ngủ quá, nói chuyện sau nhé!"),
    ("offline-no-internet.ogg", "Ôi, mất mạng rồi. Đợi mình kết nối lại nhé!"),
    ("offline-waiting.ogg", "Mình đang đợi mạng, chờ mình chút nha!"),
]

SAMPLE_RATE = 24000  # VieNeu native rate
VOICE_ID = "Ly"


def synthesize(base_url, text):
    """Call VieNeu TTS /synthesize and return PCM16 bytes."""
    resp = requests.post(
        f"{base_url}/synthesize",
        json={
            "text": text,
            "sample_rate": SAMPLE_RATE,
            "voice_id": VOICE_ID,
            "silence_p": 0.3,
            "temperature": 1.0,
            "top_k": 50,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.content


def pcm16_to_ogg(pcm_bytes, output_path, sample_rate):
    """Convert raw PCM16 bytes to OGG Vorbis file."""
    # PCM16 little-endian mono -> numpy float32
    samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    sf.write(output_path, samples, sample_rate, format="OGG", subtype="VORBIS")


def main():
    parser = argparse.ArgumentParser(description="Generate offline audio clips via VieNeu TTS")
    parser.add_argument("--url", default="http://localhost:5001", help="VieNeu TTS base URL")
    args = parser.parse_args()

    output_dir = os.path.join(os.path.dirname(__file__), "..", "audio", "offline")
    os.makedirs(output_dir, exist_ok=True)

    # Check TTS health
    try:
        health = requests.get(f"{args.url}/health", timeout=5)
        health.raise_for_status()
        print(f"TTS server healthy: {health.json().get('model', 'unknown')}")
    except Exception as e:
        print(f"ERROR: Cannot reach TTS server at {args.url}: {e}")
        sys.exit(1)

    for filename, text in CLIPS:
        output_path = os.path.join(output_dir, filename)
        print(f"Generating: {filename}")
        try:
            pcm_bytes = synthesize(args.url, text)
            pcm16_to_ogg(pcm_bytes, output_path, SAMPLE_RATE)
            size_kb = os.path.getsize(output_path) / 1024
            print(f"  OK: {size_kb:.1f} KB")
        except Exception as e:
            print(f"  FAILED: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
