"""Wrapper around faster-whisper for military voice transcription."""

from __future__ import annotations

import io
import logging
import time
from typing import Any

import numpy as np

from src.voice.config import (
    BEAM_SIZE,
    COMPUTE_TYPE,
    DEVICE,
    HOTWORDS,
    INITIAL_PROMPT,
    LANGUAGE,
    LORA_ADAPTER_PATH,
    MODEL_SIZE,
    SAMPLE_RATE,
)

logger = logging.getLogger(__name__)


class Transcriber:
    """Loads faster-whisper and transcribes audio with military vocabulary bias."""

    def __init__(self) -> None:
        self._model = None
        self._extra_prompt_terms: list[str] = []

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self, lora_path: str = LORA_ADAPTER_PATH) -> None:
        """Load the Whisper model. Call once at startup.

        Args:
            lora_path: Path to a LoRA adapter directory. If set, merges the adapter
                       with the base model and converts to CTranslate2 format for
                       faster-whisper. Empty string uses the base model directly.
        """
        from faster_whisper import WhisperModel

        device = DEVICE
        if device == "auto":
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

        compute = COMPUTE_TYPE
        if device == "cpu" and compute == "float16":
            compute = "float32"

        model_path = MODEL_SIZE

        if lora_path:
            model_path = self._merge_lora(lora_path, device)

        logger.info("Loading whisper model=%s device=%s compute=%s", model_path, device, compute)
        self._model = WhisperModel(model_path, device=device, compute_type=compute)
        logger.info("Whisper model loaded")

    @staticmethod
    def _merge_lora(lora_path: str, device: str) -> str:
        """Merge LoRA adapter with base model and convert for faster-whisper.

        Returns path to the converted CTranslate2 model directory.
        """
        import os

        ct2_path = os.path.join(os.path.dirname(lora_path), "ct2-merged")
        if os.path.exists(ct2_path):
            logger.info("Using cached merged model at %s", ct2_path)
            return ct2_path

        logger.info("Merging LoRA adapter from %s", lora_path)

        from peft import PeftModel
        from transformers import WhisperForConditionalGeneration

        base_model = WhisperForConditionalGeneration.from_pretrained(MODEL_SIZE)
        model = PeftModel.from_pretrained(base_model, lora_path)
        merged = model.merge_and_unload()

        # Save merged HF model to temp dir, then convert to CTranslate2
        import tempfile
        hf_tmp = tempfile.mkdtemp(prefix="whisper-merged-")
        merged.save_pretrained(hf_tmp)

        from faster_whisper.utils import download_model
        import ctranslate2

        # Convert HF model to CTranslate2 format
        converter = ctranslate2.converters.TransformersConverter(hf_tmp)
        converter.convert(ct2_path, quantization="float16" if device != "cpu" else "float32")

        logger.info("Merged model saved to %s", ct2_path)

        # Clean up temp HF dir
        import shutil
        shutil.rmtree(hf_tmp, ignore_errors=True)

        return ct2_path

    def transcribe(self, audio: np.ndarray | bytes, sr: int = SAMPLE_RATE) -> dict[str, Any]:
        """Transcribe audio to text.

        Args:
            audio: float32 numpy array (mono, any sample rate) or raw PCM bytes (16-bit LE).
            sr: Sample rate of the input audio.

        Returns:
            {"transcript": str, "confidence": float, "timestamp": str, "duration_s": float}
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded — call load() first")

        if isinstance(audio, bytes):
            audio = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # Resample if needed
        if sr != SAMPLE_RATE:
            import scipy.signal
            samples = int(len(audio) * SAMPLE_RATE / sr)
            audio = scipy.signal.resample(audio, samples)

        prompt = INITIAL_PROMPT
        if self._extra_prompt_terms:
            prompt += " " + " ".join(self._extra_prompt_terms)

        t0 = time.time()
        segments, info = self._model.transcribe(
            audio,
            language=LANGUAGE,
            initial_prompt=prompt,
            hotwords=HOTWORDS,
            vad_filter=True,
            beam_size=BEAM_SIZE,
        )

        texts = []
        probs = []
        for seg in segments:
            texts.append(seg.text.strip())
            probs.append(seg.avg_logprob)

        transcript = " ".join(texts).strip()
        # Convert avg log-prob to a 0-1 confidence (sigmoid-ish mapping)
        avg_prob = sum(probs) / len(probs) if probs else -1.0
        confidence = round(min(1.0, max(0.0, 1.0 + avg_prob)), 3)
        duration_s = round(time.time() - t0, 3)

        logger.info(
            "Transcribed %.1fs audio in %.1fs: '%s' (conf=%.2f)",
            len(audio) / SAMPLE_RATE,
            duration_s,
            transcript[:80],
            confidence,
        )

        return {
            "transcript": transcript,
            "confidence": confidence,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_s": duration_s,
        }

    def add_prompt_terms(self, terms: list[str]) -> None:
        """Append terms to the initial prompt for runtime prompt chaining."""
        for term in terms:
            if term not in self._extra_prompt_terms:
                self._extra_prompt_terms.append(term)
        logger.info("Prompt terms updated: %s", self._extra_prompt_terms)
