"""Configuration for the Voice ASR service."""

import os

# Service
HOST = os.getenv("VOICE_HOST", "0.0.0.0")
PORT = int(os.getenv("VOICE_PORT", "8001"))

# Whisper model — auto-select based on device
# GPU (hackathon day): large-v3-turbo (~1-2s, best accuracy)
# CPU (dev/testing): small (~2-3s, decent accuracy)
DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # "auto", "cuda", "cpu"
_auto_device = DEVICE
if _auto_device == "auto":
    try:
        import torch
        _auto_device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        _auto_device = "cpu"

_default_model = "large-v3-turbo" if _auto_device == "cuda" else "small"
MODEL_SIZE = os.getenv("WHISPER_MODEL", _default_model)
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")  # "float16", "int8", "float32"
BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1" if _auto_device == "cpu" else "5"))
LANGUAGE = "en"

# Fine-tuned model — set path to LoRA adapter dir to use it, empty string for base model
LORA_ADAPTER_PATH = os.getenv("WHISPER_LORA_ADAPTER", "")

# Military vocabulary prompt — biases Whisper toward these terms
INITIAL_PROMPT = (
    "Military radio. Grid coordinates, callsigns Alpha Bravo Charlie Delta Echo Foxtrot. "
    "Terms: overwatch, exfil, RTB, return to base, bingo fuel, CASEVAC, "
    "WILCO, Lima Charlie, niner for nine, fife for five. "
    "Vehicles: UAV, UGV, USV, drone, rover. "
    "Commands: move to, proceed to, establish, patrol, loiter, engage, classify, status, "
    "take off, takeoff, launch, land, touch down. "
    "Waypoints: Alpha, Bravo, Charlie, Delta, Echo, Foxtrot, Golf, Hotel."
)

HOTWORDS = (
    "overwatch exfil RTB bingo CASEVAC WILCO niner fife "
    "UAV UGV USV callsign grid alpha bravo charlie delta echo foxtrot golf hotel "
    "hostile friendly unknown classify engage confirm cancel "
    "takeoff take off launch land waypoint harbor citadel dockyard"
)

# VAD settings
VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.5"))
VAD_MIN_SPEECH_MS = int(os.getenv("VAD_MIN_SPEECH_MS", "250"))
VAD_SILENCE_MS = int(os.getenv("VAD_SILENCE_MS", "750"))
SAMPLE_RATE = 16000  # Whisper native rate
CHUNK_SIZE = 512  # Samples per VAD frame (~32ms at 16kHz)

# Downstream services
NLU_URL = os.getenv("NLU_URL", "http://localhost:8002/parse")
WS_HUB_URL = os.getenv("WS_HUB_URL", "ws://localhost:8005")
