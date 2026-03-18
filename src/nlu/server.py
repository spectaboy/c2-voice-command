"""FastAPI NLU service — port 8002."""

import logging
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.shared.constants import NLU_PORT
from src.shared.schemas import MilitaryCommand
from .parser import NLUParser
from .context import NLUContext

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NLU Parser", version="1.0.0")

context = NLUContext()
parser = NLUParser(context=context)


class TranscriptRequest(BaseModel):
    transcript: str
    confidence: Optional[float] = None


class CorrectionRequest(BaseModel):
    wrong_transcript: str
    wrong_parse: dict
    correct_command: dict


@app.get("/health")
async def health():
    return {"status": "ok", "service": "nlu", "port": NLU_PORT}


@app.post("/parse", response_model=list[MilitaryCommand])
async def parse_transcript(req: TranscriptRequest):
    if not req.transcript.strip():
        raise HTTPException(status_code=400, detail="Empty transcript")

    try:
        commands = parser.parse(req.transcript)
    except Exception as e:
        logger.error(f"Parse error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    if not commands:
        raise HTTPException(status_code=422, detail="Could not parse any commands from transcript")

    return commands


@app.post("/correct")
async def add_correction(req: CorrectionRequest):
    context.add_correction(req.wrong_transcript, req.wrong_parse, req.correct_command)
    return {"status": "correction_logged", "total_corrections": len(context.corrections)}


@app.get("/context")
async def get_context():
    return {
        "recent_commands": context.recent_commands,
        "corrections": context.corrections,
        "context_block": context.build_context_block(),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=NLU_PORT)
