"""Audio capture via sounddevice with push-to-talk and continuous modes."""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable

import numpy as np

from src.voice.config import CHUNK_SIZE, SAMPLE_RATE

logger = logging.getLogger(__name__)


class AudioCapture:
    """Captures audio from the default microphone.

    Supports two modes:
    - Push-to-talk: call start() / stop(), audio chunks accumulate in buffer
    - Continuous: call start_continuous(callback) to stream chunks to a callback
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, chunk_size: int = CHUNK_SIZE) -> None:
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._stream = None
        self._buffer: deque[np.ndarray] = deque(maxlen=10000)
        self._callback: Callable[[np.ndarray], None] | None = None
        self._recording = False
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """Called by sounddevice for each audio chunk."""
        if status:
            logger.warning("Audio status: %s", status)

        # Convert int16 to float32 normalized
        chunk = indata[:, 0].copy().astype(np.float32)
        if indata.dtype == np.int16:
            chunk = chunk / 32768.0

        with self._lock:
            if self._recording:
                self._buffer.append(chunk)

            if self._callback is not None:
                self._callback(chunk)

    def start(self) -> None:
        """Start push-to-talk recording."""
        import sounddevice as sd

        self._buffer.clear()
        self._recording = True

        if self._stream is None:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=self._audio_callback,
            )
            self._stream.start()
        logger.info("PTT recording started")

    def stop(self) -> np.ndarray | None:
        """Stop push-to-talk and return accumulated audio."""
        self._recording = False
        with self._lock:
            if not self._buffer:
                return None
            audio = np.concatenate(list(self._buffer))
            self._buffer.clear()
        logger.info("PTT recording stopped, %.1fs captured", len(audio) / self.sample_rate)
        return audio

    def start_continuous(self, callback: Callable[[np.ndarray], None]) -> None:
        """Start continuous capture, streaming chunks to callback."""
        import sounddevice as sd

        self._callback = callback
        self._recording = False  # Not using PTT buffer in continuous mode

        if self._stream is None:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype=np.float32,
                blocksize=self.chunk_size,
                callback=self._audio_callback,
            )
            self._stream.start()
        logger.info("Continuous capture started")

    def close(self) -> None:
        """Stop and close the audio stream."""
        self._recording = False
        self._callback = None
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Audio capture closed")
