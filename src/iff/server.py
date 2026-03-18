"""FastAPI service for the IFF classification engine.

Exposes REST endpoints for automatic and manual classification of
tracked contacts, an audit trail, and a WebSocket feed for real-time
classification-change notifications.

Run with::

    uvicorn src.iff.server:app --host 0.0.0.0 --port 8004
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.iff.audit import AuditTrail
from src.iff.contact_tracker import ContactTracker
from src.iff.entity_loader import load_entity_list
from src.iff.rules_engine import (
    DEFAULT_SENSITIVE_AREAS,
    classify_contact,
)
from src.iff.simulator import ContactSimulator
from src.tak.cot_builder import build_cot_xml
from src.tak.cot_sender import CoTSender
from src.tak.cot_type_manager import get_cot_type, update_affiliation_in_cot_type

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class ClassifyRequest(BaseModel):
    """Incoming kinematic update that triggers automatic classification."""

    uid: str
    lat: float
    lon: float
    alt: float
    heading: float
    speed: float
    domain: str = "ground"


class ManualClassifyRequest(BaseModel):
    """Operator-initiated manual classification override."""

    uid: str
    new_affiliation: Literal["f", "h", "u", "n"]


class IFFAssessmentResponse(BaseModel):
    """Result of an automatic or manual classification."""

    uid: str
    affiliation: str
    confidence: float
    threat_score: float
    indicators: list[str]
    timestamp: str


class ContactResponse(BaseModel):
    """Full state of a tracked contact."""

    uid: str
    lat: float
    lon: float
    alt: float
    heading: float
    speed: float
    affiliation: str
    threat_score: float
    confidence: float
    indicators: list[str]
    domain: str


# ---------------------------------------------------------------------------
# Global instances
# ---------------------------------------------------------------------------

tracker: ContactTracker = ContactTracker()
audit: AuditTrail = AuditTrail()
cot_sender: CoTSender = CoTSender(host="127.0.0.1", port=8087)

# Connected WebSocket clients
_ws_clients: set[WebSocket] = set()

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


_background_tasks: list[asyncio.Task] = []


async def _auto_classify_loop(interval_s: float = 3.0) -> None:
    """Periodically re-run IFF classification on all non-friendly contacts.

    This makes IFF affiliations evolve over time as simulated contacts
    move, without requiring external ``/classify`` calls.
    """
    while True:
        try:
            await asyncio.sleep(interval_s)

            all_contacts = await tracker.get_all_contacts()
            friendlies = [c for c in all_contacts if c.affiliation == "f"]

            for contact in all_contacts:
                if contact.affiliation == "f":
                    continue  # Never auto-reclassify friendlies

                prev_affiliation = contact.affiliation
                affiliation, threat_score, confidence, indicators = classify_contact(
                    contact, friendlies, DEFAULT_SENSITIVE_AREAS,
                )

                await tracker.set_classification(
                    uid=contact.uid,
                    affiliation=affiliation,
                    threat_score=threat_score,
                    confidence=confidence,
                    indicators=indicators,
                )

                if affiliation != prev_affiliation:
                    audit.add_entry(
                        uid=contact.uid,
                        previous_affiliation=prev_affiliation,
                        new_affiliation=affiliation,
                        confidence=confidence,
                        threat_score=threat_score,
                        indicators=indicators,
                        source="auto",
                    )
                    assessment = _build_assessment(
                        uid=contact.uid,
                        affiliation=affiliation,
                        confidence=confidence,
                        threat_score=threat_score,
                        indicators=indicators,
                    )
                    payload = assessment.model_dump()
                    await _broadcast_ws(payload)
                    await _notify_hub(payload)
                    logger.info(
                        "Auto-classify %s: %s → %s (score=%.2f)",
                        contact.uid, prev_affiliation, affiliation, threat_score,
                    )

                    await _push_cot(
                        uid=contact.uid,
                        lat=contact.lat,
                        lon=contact.lon,
                        alt=contact.alt,
                        heading=contact.heading,
                        speed=contact.speed,
                        domain=contact.domain,
                        affiliation=affiliation,
                    )

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in auto-classify loop")
            await asyncio.sleep(interval_s)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hook for the IFF service."""
    # Startup
    try:
        await cot_sender.connect()
        logger.info("CoTSender connected to FTS on startup")
    except OSError as exc:
        logger.warning("Could not connect to FTS on startup: %s", exc)

    # Load entity list if configured
    entity_path = os.getenv("ENTITY_LIST_PATH", "")
    if entity_path:
        count = await load_entity_list(tracker, entity_path)
        logger.info("Loaded %d entities from ENTITY_LIST_PATH=%s", count, entity_path)
    else:
        # Try default location
        default_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "entity_list.json",
        )
        if os.path.isfile(default_path):
            count = await load_entity_list(tracker, default_path)
            logger.info("Loaded %d entities from default path %s", count, default_path)

    # Start background tasks
    simulator = ContactSimulator()
    sim_task = asyncio.create_task(simulator.run(tracker, cot_sender, interval_s=1.0))
    _background_tasks.append(sim_task)
    logger.info("ContactSimulator started")

    classify_task = asyncio.create_task(_auto_classify_loop(interval_s=3.0))
    _background_tasks.append(classify_task)
    logger.info("Auto-classify loop started")

    yield

    # Shutdown
    for task in _background_tasks:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    _background_tasks.clear()

    await cot_sender.disconnect()
    logger.info("CoTSender disconnected on shutdown")


app: FastAPI = FastAPI(
    title="IFF Classification Engine",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _broadcast_ws(payload: dict) -> None:
    """Send *payload* as JSON to every connected WebSocket client."""
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_json(payload)
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _ws_clients.discard(ws)


async def _notify_hub(assessment: dict) -> None:
    """POST the classification change to the WebSocket hub (port 8005).

    If the hub is unreachable the error is logged and swallowed so that
    the calling endpoint is never blocked.
    """
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.post(
                "http://localhost:8005/broadcast",
                json={"type": "iff_change", "payload": assessment},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not notify WS hub at :8005 — %s", exc)


async def _push_cot(
    uid: str,
    lat: float,
    lon: float,
    alt: float,
    heading: float,
    speed: float,
    domain: str,
    affiliation: str,
) -> None:
    """Build a CoT XML event for the contact and send it to FTS."""
    cot_type: str = get_cot_type(domain, affiliation)
    xml: str = build_cot_xml(
        uid=uid,
        cot_type=cot_type,
        lat=lat,
        lon=lon,
        alt=alt,
        callsign=uid,
        heading=heading,
        speed=speed,
        stale_seconds=30,
    )
    sent: bool = await cot_sender.send_cot(xml)
    if not sent:
        logger.warning("Failed to send CoT for %s to FTS", uid)


def _build_assessment(
    uid: str,
    affiliation: str,
    confidence: float,
    threat_score: float,
    indicators: list[str],
) -> IFFAssessmentResponse:
    """Construct an :class:`IFFAssessmentResponse` with the current UTC timestamp."""
    return IFFAssessmentResponse(
        uid=uid,
        affiliation=affiliation,
        confidence=confidence,
        threat_score=threat_score,
        indicators=indicators,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok", "service": "iff-engine", "port": 8004}


@app.post("/classify", response_model=IFFAssessmentResponse)
async def classify(req: ClassifyRequest) -> IFFAssessmentResponse:
    """Accept a kinematic update, run the rules engine, and return the assessment."""
    # 1. Upsert the contact with latest kinematics
    contact = await tracker.update_contact(
        uid=req.uid,
        lat=req.lat,
        lon=req.lon,
        alt=req.alt,
        heading=req.heading,
        speed=req.speed,
        domain=req.domain,
    )

    # 2. Gather friendlies for the rules engine
    friendlies = await tracker.get_friendlies()

    # 3. Run classification
    affiliation, threat_score, confidence, indicators = classify_contact(
        contact, friendlies, DEFAULT_SENSITIVE_AREAS,
    )

    # 4. Check for change & update tracker
    prev_affiliation: str = contact.affiliation
    await tracker.set_classification(
        uid=req.uid,
        affiliation=affiliation,
        threat_score=threat_score,
        confidence=confidence,
        indicators=indicators,
    )

    # 5. Build response
    assessment = _build_assessment(
        uid=req.uid,
        affiliation=affiliation,
        confidence=confidence,
        threat_score=threat_score,
        indicators=indicators,
    )

    # 6. If classification changed, log and broadcast
    if affiliation != prev_affiliation:
        audit.add_entry(
            uid=req.uid,
            previous_affiliation=prev_affiliation,
            new_affiliation=affiliation,
            confidence=confidence,
            threat_score=threat_score,
            indicators=indicators,
            source="auto",
        )
        payload = assessment.model_dump()
        await _broadcast_ws(payload)
        await _notify_hub(payload)

    # 7. Push updated CoT to FTS
    await _push_cot(
        uid=req.uid,
        lat=req.lat,
        lon=req.lon,
        alt=req.alt,
        heading=req.heading,
        speed=req.speed,
        domain=req.domain,
        affiliation=affiliation,
    )

    return assessment


@app.post("/manual-classify", response_model=IFFAssessmentResponse)
async def manual_classify(req: ManualClassifyRequest) -> IFFAssessmentResponse:
    """Operator-initiated manual classification override."""
    contact = await tracker.get_contact(req.uid)
    if contact is None:
        raise HTTPException(status_code=404, detail=f"Contact {req.uid!r} not found")

    prev_affiliation: str = contact.affiliation

    # Manual override: threat_score and confidence are set to reflect certainty
    if req.new_affiliation == "h":
        threat_score = 1.0
    elif req.new_affiliation == "f":
        threat_score = 0.0
    elif req.new_affiliation == "n":
        threat_score = 0.0
    else:
        threat_score = 0.5

    confidence = 1.0
    indicators = [f"Manual override to '{req.new_affiliation}' by operator"]

    await tracker.set_classification(
        uid=req.uid,
        affiliation=req.new_affiliation,
        threat_score=threat_score,
        confidence=confidence,
        indicators=indicators,
    )

    assessment = _build_assessment(
        uid=req.uid,
        affiliation=req.new_affiliation,
        confidence=confidence,
        threat_score=threat_score,
        indicators=indicators,
    )

    # Always log manual overrides to audit
    audit.add_entry(
        uid=req.uid,
        previous_affiliation=prev_affiliation,
        new_affiliation=req.new_affiliation,
        confidence=confidence,
        threat_score=threat_score,
        indicators=indicators,
        source="manual",
    )

    # Broadcast change
    payload = assessment.model_dump()
    await _broadcast_ws(payload)
    await _notify_hub(payload)

    # Push updated CoT
    await _push_cot(
        uid=req.uid,
        lat=contact.lat,
        lon=contact.lon,
        alt=contact.alt,
        heading=contact.heading,
        speed=contact.speed,
        domain=contact.domain,
        affiliation=req.new_affiliation,
    )

    return assessment


@app.get("/contacts", response_model=list[ContactResponse])
async def get_contacts() -> list[ContactResponse]:
    """Return every tracked contact with its current classification."""
    contacts = await tracker.get_all_contacts()
    return [
        ContactResponse(
            uid=c.uid,
            lat=c.lat,
            lon=c.lon,
            alt=c.alt,
            heading=c.heading,
            speed=c.speed,
            affiliation=c.affiliation,
            threat_score=c.threat_score,
            confidence=c.confidence,
            indicators=c.indicators,
            domain=c.domain,
        )
        for c in contacts
    ]


@app.get("/contact/{uid}", response_model=Optional[ContactResponse])
async def get_contact(uid: str) -> ContactResponse:
    """Return a single tracked contact by UID.

    Used by the Coordinator to check IFF status before routing ENGAGE commands.
    """
    contact = await tracker.get_contact(uid)
    if contact is None:
        raise HTTPException(status_code=404, detail=f"Contact {uid!r} not tracked")
    return ContactResponse(
        uid=contact.uid,
        lat=contact.lat,
        lon=contact.lon,
        alt=contact.alt,
        heading=contact.heading,
        speed=contact.speed,
        affiliation=contact.affiliation,
        threat_score=contact.threat_score,
        confidence=contact.confidence,
        indicators=contact.indicators,
        domain=contact.domain,
    )


class LoadEntitiesRequest(BaseModel):
    path: str


@app.post("/load-entities")
async def load_entities(req: LoadEntitiesRequest) -> dict:
    """Load an entity list JSON file into the contact tracker."""
    count = await load_entity_list(tracker, req.path)
    return {"status": "ok", "loaded": count, "path": req.path}


@app.get("/audit")
async def get_audit(count: int = Query(default=50, ge=1)) -> list[dict]:
    """Return the most recent audit trail entries."""
    entries = audit.get_recent(count)
    return audit.to_dicts(entries)


@app.websocket("/ws/iff")
async def ws_iff(ws: WebSocket) -> None:
    """WebSocket feed for real-time IFF classification changes."""
    await ws.accept()
    _ws_clients.add(ws)
    logger.info("WebSocket client connected (%d total)", len(_ws_clients))
    try:
        while True:
            # Keep the connection alive; we only send, but must read to
            # detect disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(_ws_clients))
