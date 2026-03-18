"""FastAPI server for the Voice ASR service."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import wave

import numpy as np
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.voice.config import HOST, NLU_URL, PORT, SAMPLE_RATE, WS_HUB_URL
from src.voice.transcriber import Transcriber
from src.voice.tts import speak_with_effects
from src.voice.vad import VADProcessor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice ASR Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

transcriber = Transcriber()
vad = VADProcessor()


@app.on_event("startup")
async def startup() -> None:
    transcriber.load()
    vad.load()


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok" if transcriber.is_loaded else "loading",
        "service": "voice-asr",
        "port": PORT,
    }


@app.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    """Accept an audio file (WAV/WebM/OGG) and return transcription."""
    raw = await file.read()

    content_type = file.content_type or ""
    filename = file.filename or ""

    # Try to read as WAV to extract PCM
    if "wav" in content_type or filename.endswith(".wav"):
        audio_bytes, sr = _read_wav(raw)
        result = transcriber.transcribe(audio_bytes, sr=sr)
    else:
        # For non-WAV, let faster-whisper handle decoding via ffmpeg
        # Write to a temp buffer and pass the raw bytes
        import tempfile, os
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(raw)
            tmp_path = tmp.name
        try:
            import numpy as np
            # faster-whisper can decode from file path
            result = _transcribe_from_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    return result


def _read_wav(raw: bytes) -> tuple[bytes, int]:
    """Extract PCM data and sample rate from WAV bytes."""
    with wave.open(io.BytesIO(raw), "rb") as wf:
        sr = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, sr


def _transcribe_from_file(path: str) -> dict:
    """Transcribe directly from a file path (non-WAV formats)."""
    import time
    import numpy as np

    if not transcriber.is_loaded:
        raise RuntimeError("Model not loaded")

    from src.voice.config import (
        BEAM_SIZE, HOTWORDS, INITIAL_PROMPT, LANGUAGE,
    )

    t0 = time.time()
    segments, info = transcriber._model.transcribe(
        path,
        language=LANGUAGE,
        initial_prompt=INITIAL_PROMPT,
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
    avg_prob = sum(probs) / len(probs) if probs else -1.0
    confidence = round(min(1.0, max(0.0, 1.0 + avg_prob)), 3)

    return {
        "transcript": transcript,
        "confidence": confidence,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_s": round(time.time() - t0, 3),
    }


@app.post("/readback")
async def readback(body: dict) -> dict:
    """Speak a readback message via TTS for command confirmation.

    Body: {"text": str, "command_id": str}
    The coordinator calls this when a command requires voice confirmation.
    TTS speaks the readback; the operator then confirms/cancels via PTT.
    """
    text = body.get("text", "")
    command_id = body.get("command_id", "")

    if not text:
        return {"status": "error", "message": "No text provided"}

    logger.info("TTS readback for command %s: %s", command_id, text[:80])
    asyncio.create_task(speak_with_effects(text))

    if command_id:
        set_pending_confirmation(command_id)

    return {"status": "ok", "command_id": command_id, "message": "Readback initiated"}


@app.websocket("/ws/voice")
async def ws_voice(ws: WebSocket) -> None:
    """WebSocket endpoint for real-time voice streaming.

    Client sends:
      - Binary frames: raw 16kHz 16-bit mono PCM audio chunks
      - Text frames: JSON control messages
        {"type": "ptt_start"} — begin push-to-talk capture
        {"type": "ptt_stop"}  — end push-to-talk, trigger transcription
        {"type": "mode", "mode": "ptt" | "continuous"}

    Server sends:
      - JSON: {"transcript", "confidence", "timestamp", "is_final"}
    """
    await ws.accept()
    mode = "ptt"  # "ptt" or "continuous"
    ptt_buffer: list[np.ndarray] = []
    ptt_active = False

    logger.info("WebSocket voice client connected")

    try:
        while True:
            msg = await ws.receive()

            if "text" in msg:
                data = json.loads(msg["text"])
                msg_type = data.get("type", "")

                if msg_type == "ptt_start":
                    ptt_active = True
                    ptt_buffer.clear()
                    vad.reset()
                    logger.debug("PTT start")

                elif msg_type == "ptt_stop":
                    ptt_active = False
                    if ptt_buffer:
                        audio = np.concatenate(ptt_buffer)
                        ptt_buffer.clear()
                        result = transcriber.transcribe(audio)
                        result["is_final"] = True
                        await ws.send_json(result)
                        asyncio.create_task(_emit_transcript(result))
                    logger.debug("PTT stop")

                elif msg_type == "mode":
                    mode = data.get("mode", "ptt")
                    vad.reset()
                    logger.info("Mode switched to %s", mode)

            elif "bytes" in msg:
                chunk = np.frombuffer(msg["bytes"], dtype=np.int16).astype(np.float32) / 32768.0

                if mode == "ptt" and ptt_active:
                    ptt_buffer.append(chunk)

                elif mode == "continuous":
                    segment_ready = vad.process(chunk)
                    if segment_ready:
                        segment = vad.get_segment()
                        if segment is not None and len(segment) > SAMPLE_RATE * 0.3:
                            result = transcriber.transcribe(segment)
                            result["is_final"] = True
                            await ws.send_json(result)
                            asyncio.create_task(_emit_transcript(result))

    except WebSocketDisconnect:
        logger.info("WebSocket voice client disconnected")


# Pending confirmation state: command_id -> True when awaiting confirm/cancel
_pending_confirmation: dict[str, str] = {}


def set_pending_confirmation(command_id: str) -> None:
    """Mark a command as awaiting voice confirmation."""
    _pending_confirmation["active"] = command_id
    logger.info("Awaiting voice confirmation for command %s", command_id)


async def _emit_transcript(result: dict) -> None:
    """Forward transcript to NLU service and WebSocket hub.

    If a confirmation is pending, check for CONFIRM/CANCEL first.
    """
    import httpx

    transcript = result["transcript"].strip().upper()

    # Check for confirmation response
    if "active" in _pending_confirmation:
        command_id = _pending_confirmation.pop("active")
        if "CONFIRM" in transcript:
            await _send_confirmation(command_id, confirmed=True)
            return
        elif "CANCEL" in transcript or "ABORT" in transcript or "NEGATIVE" in transcript:
            await _send_confirmation(command_id, confirmed=False)
            return

    payload = {
        "transcript": result["transcript"],
        "confidence": result["confidence"],
    }

    # POST to NLU
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(NLU_URL, json=payload)
            logger.info("NLU response: %s", resp.status_code)
    except Exception as e:
        logger.warning("Failed to reach NLU at %s: %s", NLU_URL, e)

    # Send to WebSocket hub
    try:
        import websockets
        ws_msg = {
            "type": "voice_transcript",
            "payload": {
                "transcript": result["transcript"],
                "confidence": result["confidence"],
                "timestamp": result["timestamp"],
            },
        }
        async with websockets.connect(WS_HUB_URL) as hub:
            await hub.send(json.dumps(ws_msg))
    except Exception as e:
        logger.warning("Failed to reach WS hub at %s: %s", WS_HUB_URL, e)


async def _send_confirmation(command_id: str, confirmed: bool) -> None:
    """POST confirmation result to the coordinator."""
    import httpx

    coordinator_url = f"http://localhost:8000/confirm/{command_id}"
    payload = {"confirmed": confirmed}

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(coordinator_url, json=payload)
            logger.info(
                "Confirmation %s for %s: coordinator responded %s",
                "CONFIRMED" if confirmed else "CANCELLED",
                command_id,
                resp.status_code,
            )
    except Exception as e:
        logger.warning("Failed to send confirmation to coordinator: %s", e)

    # TTS feedback
    if confirmed:
        asyncio.create_task(speak_with_effects("Confirmed. Executing."))
    else:
        asyncio.create_task(speak_with_effects("Cancelled."))


def main() -> None:
    import uvicorn
    uvicorn.run("src.voice.server:app", host=HOST, port=PORT, reload=True)


if __name__ == "__main__":
    main()
