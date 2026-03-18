"""Silero VAD integration for speech endpoint detection."""

from __future__ import annotations

import logging
from collections import deque

import numpy as np

from src.voice.config import (
    CHUNK_SIZE,
    SAMPLE_RATE,
    VAD_MIN_SPEECH_MS,
    VAD_SILENCE_MS,
    VAD_THRESHOLD,
)

logger = logging.getLogger(__name__)


class VADProcessor:
    """Detects speech onset and offset using Silero VAD.

    Feed 16kHz mono float32 audio chunks via process(). When a complete
    speech segment is detected (speech followed by sufficient silence),
    get_segment() returns the accumulated audio.
    """

    def __init__(self) -> None:
        self._model = None
        self._speech_buffer: list[np.ndarray] = []
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0

        # How many consecutive frames count as speech onset / silence offset
        self._min_speech_frames = max(1, int(VAD_MIN_SPEECH_MS / 1000 * SAMPLE_RATE / CHUNK_SIZE))
        self._max_silence_frames = max(1, int(VAD_SILENCE_MS / 1000 * SAMPLE_RATE / CHUNK_SIZE))

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        """Load the Silero VAD model."""
        import torch

        logger.info("Loading Silero VAD model")
        self._model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        self._model.eval()
        logger.info("Silero VAD loaded")

    def reset(self) -> None:
        """Reset state for a new utterance."""
        self._speech_buffer.clear()
        self._is_speaking = False
        self._silence_frames = 0
        self._speech_frames = 0
        if self._model is not None:
            self._model.reset_states()

    def process(self, chunk: np.ndarray) -> bool:
        """Process an audio chunk and return True if a complete segment is ready.

        Args:
            chunk: float32 mono audio, length should be CHUNK_SIZE (512 samples at 16kHz).

        Returns:
            True if a complete speech segment is ready to retrieve via get_segment().
        """
        if not self.is_loaded:
            raise RuntimeError("VAD model not loaded — call load() first")

        import torch

        tensor = torch.from_numpy(chunk).float()
        if tensor.dim() == 1:
            tensor = tensor.unsqueeze(0)

        prob = self._model(tensor, SAMPLE_RATE).item()

        if prob >= VAD_THRESHOLD:
            self._speech_frames += 1
            self._silence_frames = 0

            if self._speech_frames >= self._min_speech_frames:
                if not self._is_speaking:
                    logger.debug("Speech onset detected (prob=%.2f)", prob)
                self._is_speaking = True

            if self._is_speaking:
                self._speech_buffer.append(chunk.copy())
        else:
            if self._is_speaking:
                # Still accumulate audio during short silences
                self._speech_buffer.append(chunk.copy())
                self._silence_frames += 1

                if self._silence_frames >= self._max_silence_frames:
                    logger.debug(
                        "Speech offset detected after %dms silence",
                        self._silence_frames * CHUNK_SIZE * 1000 // SAMPLE_RATE,
                    )
                    return True  # Segment ready
            else:
                self._speech_frames = 0

        return False

    def get_segment(self) -> np.ndarray | None:
        """Retrieve the accumulated speech segment and reset.

        Returns:
            float32 numpy array of the speech audio, or None if no segment.
        """
        if not self._speech_buffer:
            return None

        segment = np.concatenate(self._speech_buffer)
        self.reset()
        return segment
