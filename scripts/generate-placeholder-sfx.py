"""Generate placeholder SFX OGG files using pure sine wave tones.

No external dependencies beyond numpy and soundfile.
Creates short beeps/tones for each SFX type in audio/sfx/.

Usage:
    python scripts/generate-placeholder-sfx.py
"""

import os

import numpy as np
import soundfile as sf

SAMPLE_RATE = 24000
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "audio", "sfx")

# (filename, frequency_hz, duration_s, style)
# style: "beep" = simple tone, "rising" = ascending pitch, "falling" = descending pitch
SFX_SPECS = [
    ("eat.ogg", 440, 0.3, "beep"),
    ("level-up.ogg", 523, 0.6, "rising"),
    ("badge-earned.ogg", 659, 0.4, "beep"),
    ("evolution.ogg", 392, 1.0, "rising"),
    ("transform.ogg", 440, 0.5, "rising"),
    ("warning.ogg", 330, 0.8, "falling"),
    ("regression.ogg", 262, 1.0, "falling"),
    ("quest-start.ogg", 587, 0.4, "beep"),
]


def generate_tone(freq_hz, duration_s, style):
    """Generate a mono float32 audio array."""
    t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)

    if style == "rising":
        freq = np.linspace(freq_hz, freq_hz * 2, len(t))
        signal = np.sin(2 * np.pi * freq * t)
    elif style == "falling":
        freq = np.linspace(freq_hz, freq_hz * 0.5, len(t))
        signal = np.sin(2 * np.pi * freq * t)
    else:  # beep: two short pips
        half = len(t) // 2
        envelope = np.zeros(len(t))
        envelope[:half] = 1.0
        envelope[int(half * 1.2):] = 1.0
        signal = np.sin(2 * np.pi * freq_hz * t) * envelope

    # Fade in/out to avoid clicks (10ms)
    fade = int(0.01 * SAMPLE_RATE)
    signal[:fade] *= np.linspace(0, 1, fade)
    signal[-fade:] *= np.linspace(1, 0, fade)

    # Normalize to 0.7 peak
    signal = signal * 0.7 / max(np.abs(signal).max(), 1e-6)
    return signal.astype(np.float32)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for filename, freq, duration, style in SFX_SPECS:
        path = os.path.join(OUTPUT_DIR, filename)
        signal = generate_tone(freq, duration, style)
        sf.write(path, signal, SAMPLE_RATE, format="OGG", subtype="VORBIS")
        size_kb = os.path.getsize(path) / 1024
        print(f"{filename:25s} {duration:.1f}s  {style:8s}  {size_kb:.1f} KB")

    print(f"\nGenerated {len(SFX_SPECS)} SFX files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
