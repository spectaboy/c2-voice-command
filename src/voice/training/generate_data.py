"""Generate synthetic military radio training data using Edge TTS + audiomentations.

Produces ~1,050 samples across 6 voice variants with radio-style augmentation.
Output: a directory of WAV files + a manifest CSV (path, transcript).

Usage:
    python -m src.voice.training.generate_data --out-dir data/training --count 1050
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import logging
import os
import random
import wave

import numpy as np

logger = logging.getLogger(__name__)

# Voice variants for diversity
VOICES = [
    "en-US-GuyNeural",
    "en-US-ChristopherNeural",
    "en-US-EricNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-GB-RyanNeural",
]

# Rate variations to simulate different speaking styles
RATES = ["-5%", "+0%", "+10%", "+15%"]

# Military command templates
TEMPLATES = [
    # Move commands
    "{callsign}, proceed to grid {grid}",
    "{callsign}, move to grid reference {grid}",
    "Send {callsign} to grid {grid}",
    "{callsign}, advance to position {grid}",
    # Overwatch
    "{callsign}, establish overwatch at grid {grid}",
    "{callsign}, set up overwatch position grid {grid}",
    # RTB
    "{callsign}, return to base",
    "{callsign}, RTB immediately",
    "All units, return to base",
    # Patrol
    "{callsign}, patrol route {route}",
    "{callsign}, begin patrol pattern along route {route}",
    # Loiter
    "{callsign}, loiter at current position",
    "{callsign}, hold position and loiter",
    "{callsign}, orbit grid {grid}",
    # Status
    "{callsign}, report status",
    "What is {callsign} status",
    "Give me status on {callsign}",
    # Classify
    "Classify contact {contact} as {affiliation}",
    "Mark contact {contact} {affiliation}",
    "{contact} is {affiliation}",
    # Multi-vehicle
    "All units, establish harbor defense pattern",
    "All UAVs, move to grid {grid}",
    "All ground units, patrol perimeter",
    # Engage (high-risk)
    "Engage hostile contact {contact}",
    "{callsign}, engage target at grid {grid}",
    # Confirmation responses
    "Confirm",
    "Cancel",
    "Affirmative",
    "Negative",
    "Roger",
    "Wilco",
    # Natural phrasing
    "I need {callsign} at grid {grid} ASAP",
    "Get the drone to grid {grid}",
    "Have {callsign} establish overwatch over grid {grid}",
    "Bring {callsign} back home",
    "Where is {callsign} right now",
]

CALLSIGNS = [
    "UAV-1", "UAV-2", "UAV-3", "UGV-1", "UGV-2", "USV-1",
    "Alpha", "Bravo", "Charlie", "Delta",
    "the drone", "the rover", "the boat",
]

GRIDS = [
    "four four seven", "niner two three", "one fife eight",
    "three seven niner", "six two four", "eight one six",
    "four four seven two", "niner niner zero one",
]

ROUTES = ["Alpha", "Bravo", "Charlie", "perimeter", "coastal"]

CONTACTS = ["alpha-seven", "bravo-three", "contact-one", "unknown-two", "tango-niner"]

AFFILIATIONS = ["hostile", "friendly", "unknown", "neutral"]


def _fill_template(template: str) -> str:
    """Fill a template with random values."""
    return template.format(
        callsign=random.choice(CALLSIGNS),
        grid=random.choice(GRIDS),
        route=random.choice(ROUTES),
        contact=random.choice(CONTACTS),
        affiliation=random.choice(AFFILIATIONS),
    )


async def _synthesize_one(text: str, voice: str, rate: str, max_retries: int = 5) -> bytes:
    """Generate WAV audio for one sentence, with retry on rate-limit."""
    import edge_tts

    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(text, voice, rate=rate)
            mp3_buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_buf.write(chunk["data"])

            mp3_bytes = mp3_buf.getvalue()
            if not mp3_bytes:
                return b""

            return _mp3_to_wav(mp3_bytes)
        except Exception as e:
            wait = 2 ** attempt + random.random() * 2
            logger.warning("TTS attempt %d failed (%s), retrying in %.1fs", attempt + 1, e, wait)
            await asyncio.sleep(wait)

    logger.error("TTS failed after %d retries for: %s", max_retries, text[:50])
    return b""


def _mp3_to_wav(mp3_bytes: bytes) -> bytes:
    """Decode MP3 bytes to 16kHz mono int16 WAV using miniaudio (no ffmpeg needed)."""
    import miniaudio
    import wave as wave_mod

    decoded = miniaudio.decode(mp3_bytes, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=16000)
    samples = np.frombuffer(decoded.samples, dtype=np.int16)

    buf = io.BytesIO()
    with wave_mod.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()


def _augment_audio(wav_bytes: bytes) -> bytes:
    """Apply radio-style augmentation to WAV audio.

    Augmentations:
    - Bandpass filter (200-4000 Hz) to simulate radio
    - Gaussian noise for static
    - Clipping distortion for overdriven comms
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        sr = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    # Bandpass filter (200-4000 Hz) — simplified via FFT
    if len(samples) > 0:
        freqs = np.fft.rfftfreq(len(samples), 1.0 / sr)
        fft = np.fft.rfft(samples)
        mask = (freqs >= 200) & (freqs <= 4000)
        fft[~mask] *= 0.05  # Attenuate rather than zero
        samples = np.fft.irfft(fft, n=len(samples))

    # Gaussian noise (radio static)
    noise_level = random.uniform(0.005, 0.03)
    samples += np.random.randn(len(samples)).astype(np.float32) * noise_level

    # Random clipping distortion (30% chance)
    if random.random() < 0.3:
        clip_level = random.uniform(0.7, 0.95)
        samples = np.clip(samples, -clip_level, clip_level)

    # Normalize
    peak = np.abs(samples).max()
    if peak > 0:
        samples = samples / peak * 0.9

    # Back to int16 WAV
    pcm_out = (samples * 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_out)
    return buf.getvalue()


async def generate_dataset(out_dir: str, count: int = 1050) -> str:
    """Generate the full synthetic training dataset.

    Returns path to the manifest CSV.
    """
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.csv")

    # Load existing manifest to resume from where we left off
    existing = set()
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            existing = {r["path"] for r in rows}
        logger.info("Resuming: %d samples already exist", len(existing))
    else:
        rows = []

    for i in range(count):
        filename = f"sample_{i:05d}.wav"
        if filename in existing:
            continue

        template = random.choice(TEMPLATES)
        text = _fill_template(template)
        voice = random.choice(VOICES)
        rate = random.choice(RATES)

        wav_bytes = await _synthesize_one(text, voice, rate)
        if not wav_bytes:
            logger.warning("Empty audio for sample %d: %s", i, text[:50])
            continue

        # Augment 70% of samples
        if random.random() < 0.7:
            wav_bytes = _augment_audio(wav_bytes)

        filepath = os.path.join(out_dir, filename)
        with open(filepath, "wb") as f:
            f.write(wav_bytes)

        rows.append({"path": filename, "transcript": text})

        if (i + 1) % 50 == 0:
            logger.info("Generated %d/%d samples", len(rows), count)

        # Small delay to avoid rate-limiting
        await asyncio.sleep(0.15)

    with open(manifest_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["path", "transcript"])
        writer.writeheader()
        writer.writerows(rows)

    logger.info("Dataset complete: %d samples in %s", len(rows), out_dir)
    return manifest_path


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Generate synthetic military radio training data")
    parser.add_argument("--out-dir", default="data/training", help="Output directory")
    parser.add_argument("--count", type=int, default=1050, help="Number of samples")
    args = parser.parse_args()

    asyncio.run(generate_dataset(args.out_dir, args.count))


if __name__ == "__main__":
    main()
