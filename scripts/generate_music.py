import wave
import struct
import math
import random
from pathlib import Path

SAMPLE_RATE = 44100
DURATION = 30  # seconds per track
ASSETS_DIR = Path(__file__).parent.parent / "assets"
MUSIC_DIR = ASSETS_DIR / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)


def note_freq(n: int) -> float:
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


def generate_piano(note: int, t: float, velocity: float = 0.6) -> float:
    freq = note_freq(note)
    env = math.exp(-t * 3.0)
    fundamental = math.sin(2.0 * math.pi * freq * t)
    h2 = 0.5 * math.sin(2.0 * math.pi * freq * 2.0 * t)
    h3 = 0.25 * math.sin(2.0 * math.pi * freq * 3.0 * t)
    return velocity * env * (fundamental + h2 + h3) * 0.5


def generate_pad(note: int, t: float, velocity: float = 0.4) -> float:
    freq = note_freq(note)
    env = min(1.0, t * 4.0) * math.exp(-t * 1.5)
    fundamental = math.sin(2.0 * math.pi * freq * t)
    fifth = 0.4 * math.sin(2.0 * math.pi * freq * 1.5 * t)
    return velocity * env * (fundamental + fifth) * 0.35


def generate_pluck(note: int, t: float, velocity: float = 0.5) -> float:
    freq = note_freq(note)
    env = math.exp(-t * 5.0)
    body = math.sin(2.0 * math.pi * freq * t)
    brightness = 0.3 * math.sin(2.0 * math.pi * freq * 4.0 * t) * math.exp(-t * 12.0)
    return velocity * env * (body + brightness) * 0.4


def generate_guitar(note: int, t: float, velocity: float = 0.5) -> float:
    freq = note_freq(note)
    env = math.exp(-t * 2.5)
    fundamental = math.sin(2.0 * math.pi * freq * t)
    overtone = 0.2 * math.sin(2.0 * math.pi * freq * 2.01 * t) * math.exp(-t * 3.5)
    return velocity * env * (fundamental + overtone) * 0.5


def write_wav(filename: str, samples: list[float]):
    path = MUSIC_DIR / filename
    max_val = max(max(abs(s) for s in samples), 0.01)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        for s in samples:
            v = int(s / max_val * 28000)
            v = max(-32767, min(32767, v))
            wf.writeframesraw(struct.pack("<hh", v, v))
    print(f"  Created: {path} ({len(samples) / SAMPLE_RATE:.0f}s)")


def make_track(filename: str, generator, progression: list[list[int]],
               bpm: int = 80, pattern: list[float] | None = None,
               sustain: float = 1.5):
    total_samples = SAMPLE_RATE * DURATION
    beat_s = 60.0 / bpm
    if pattern is None:
        pattern = [0, 2, 4, 6]
    pattern_len = len(pattern)

    samples = [0.0] * total_samples

    for bar in range(0, int(DURATION / (beat_s * 4)) + 10):
        chord = progression[bar % len(progression)]
        bar_start = bar * beat_s * 4
        for j, offset in enumerate(pattern):
            note_idx = j % len(chord)
            if note_idx < len(chord):
                note = chord[note_idx]
                start_t = bar_start + offset * beat_s
                start_sample = int(start_t * SAMPLE_RATE)
                note_samples = int(sustain * SAMPLE_RATE)
                for k in range(note_samples):
                    idx = start_sample + k
                    if 0 <= idx < total_samples:
                        t = k / SAMPLE_RATE
                        v = generator(note - 12 if generator == generate_pad else note, t)
                        samples[idx] += v

    write_wav(filename, samples)


# Light piano - gentle C major arpeggios
def make_light_piano():
    progression = [
        [60, 64, 67],  # C major
        [62, 65, 69],  # D minor
        [59, 62, 67],  # G major
        [60, 64, 67],  # C major
    ]
    pattern = [0, 1.5, 3, 4.5, 0, 2.5, 1, 3.5]
    make_track(
        "light_piano.wav",
        generate_piano,
        progression,
        bpm=72,
        pattern=pattern,
        sustain=2.0,
    )


# Calm guitar - simple fingerpicking
def make_calm_guitar():
    progression = [
        [64, 67, 71],
        [65, 69, 72],
        [67, 71, 74],
        [65, 69, 72],
    ]
    pattern = [0, 1, 2, 3, 0, 2, 1, 3]
    make_track(
        "calm_guitar.wav",
        generate_guitar,
        progression,
        bpm=90,
        pattern=pattern,
        sustain=1.8,
    )


# Ukulele happy - bright C major
def make_ukulele_happy():
    progression = [
        [60, 64, 67],
        [64, 67, 71],
        [65, 69, 72],
        [67, 71, 74],
    ]
    pattern = [0, 1, 2, 3, 2, 1, 3, 0]
    make_track(
        "ukulele_happy.wav",
        generate_pluck,
        progression,
        bpm=110,
        pattern=pattern,
        sustain=1.2,
    )


# Ambient soft - atmospheric pads
def make_ambient_soft():
    progression = [
        [60, 64, 67, 71],
        [59, 62, 67, 71],
        [57, 60, 65, 69],
        [55, 59, 62, 67],
    ]
    pattern = [0, 4, 8, 12]
    make_track(
        "ambient_soft.wav",
        generate_pad,
        progression,
        bpm=60,
        pattern=pattern,
        sustain=4.0,
    )


def main():
    print("Generating background music tracks...")
    print()

    print("[1/4] light_piano.wav (light piano arpeggios, C major, 72 bpm)")
    make_light_piano()

    print("[2/4] calm_guitar.wav (gentle fingerpicking, 90 bpm)")
    make_calm_guitar()

    print("[3/4] ukulele_happy.wav (bright plucked, 110 bpm)")
    make_ukulele_happy()

    print("[4/4] ambient_soft.wav (atmospheric pads, 60 bpm)")
    make_ambient_soft()

    print()
    print("Done! 4 background music tracks generated in assets/music/")
    print()
    print("These are synthesized placeholder tracks.")
    print("For production use, replace with real royalty-free music from:")
    print("  - https://pixabay.com/music/")
    print("  - https://uppbeat.io/ (free tier)")
    print("  - https://www.youtube.com/audiolibrary")


if __name__ == "__main__":
    main()
