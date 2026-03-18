"""Text-to-speech via edge-tts with military radio styling."""

from __future__ import annotations

import asyncio
import io
import logging

import numpy as np

from src.voice.config import SAMPLE_RATE

logger = logging.getLogger(__name__)

# Military-sounding male voice
VOICE = "en-US-GuyNeural"
RATE = "+10%"  # Slightly faster for radio cadence
VOLUME = "+0%"


async def synthesize(text: str) -> bytes:
    """Generate speech audio from text using Edge TTS.

    Returns:
        Raw PCM bytes (16kHz mono int16).
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, VOICE, rate=RATE, volume=VOLUME)

    # edge-tts outputs mp3 — collect chunks then decode
    mp3_buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_buf.write(chunk["data"])

    mp3_bytes = mp3_buf.getvalue()
    if not mp3_bytes:
        logger.warning("TTS produced empty audio for: %s", text[:60])
        return b""

    pcm = _decode_mp3_to_pcm(mp3_bytes)
    return pcm


def _decode_mp3_to_pcm(mp3_bytes: bytes) -> bytes:
    """Decode MP3 bytes to 16kHz mono int16 PCM using miniaudio."""
    import miniaudio

    try:
        decoded = miniaudio.decode(mp3_bytes, output_format=miniaudio.SampleFormat.SIGNED16,
                                   nchannels=1, sample_rate=SAMPLE_RATE)
        return bytes(decoded.samples)
    except Exception as e:
        logger.error("MP3 decode failed: %s", e)
        return b""


async def speak(text: str) -> None:
    """Synthesize text and play through speakers."""
    pcm = await synthesize(text)
    if not pcm:
        return

    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

    try:
        import sounddevice as sd
        sd.play(samples, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception as e:
        logger.error("Audio playback failed: %s", e)


async def speak_with_effects(text: str, beep: bool = True) -> None:
    """Speak with radio-style effects: beep before, static texture."""
    if beep:
        _play_beep()

    await speak(text)


def _play_beep(freq: float = 1000.0, duration_s: float = 0.08) -> None:
    """Play a short acknowledgment beep."""
    try:
        import sounddevice as sd

        t = np.linspace(0, duration_s, int(SAMPLE_RATE * duration_s), endpoint=False)
        # Beep with quick fade-in/out
        envelope = np.ones_like(t)
        fade = int(SAMPLE_RATE * 0.01)
        envelope[:fade] = np.linspace(0, 1, fade)
        envelope[-fade:] = np.linspace(1, 0, fade)
        tone = (np.sin(2 * np.pi * freq * t) * 0.3 * envelope).astype(np.float32)

        sd.play(tone, samplerate=SAMPLE_RATE)
        sd.wait()
    except Exception as e:
        logger.debug("Beep playback failed: %s", e)


def add_radio_static(audio: np.ndarray, intensity: float = 0.02) -> np.ndarray:
    """Add subtle radio static noise to audio for immersion."""
    noise = np.random.randn(len(audio)).astype(np.float32) * intensity
    return np.clip(audio + noise, -1.0, 1.0)
