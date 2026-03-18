"""Build Cursor-on-Target (CoT) XML strings for FreeTAKServer.

Pure-Python implementation using only stdlib xml.etree.ElementTree.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Duck-typed protocol for CoTEvent (owned by src/shared)
# ---------------------------------------------------------------------------

@runtime_checkable
class CoTEventLike(Protocol):
    """Structural type matching the CoTEvent Pydantic model."""

    uid: str
    cot_type: str
    lat: float
    lon: float
    alt_m: float
    callsign: str
    heading: float
    speed_mps: float
    stale_seconds: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    """Return the current UTC time (seam for testing)."""
    return datetime.now(timezone.utc)


def _format_iso(dt: datetime) -> str:
    """Format *dt* as ISO 8601 with milliseconds and a trailing 'Z'."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cot_xml(
    uid: str,
    cot_type: str,
    lat: float,
    lon: float,
    alt: float,
    callsign: str,
    heading: float = 0.0,
    speed: float = 0.0,
    stale_seconds: int = 30,
) -> str:
    """Return a complete CoT XML event string.

    Parameters
    ----------
    uid:
        Unique identifier for the entity.
    cot_type:
        CoT type string (e.g. ``"a-f-G-U-C"``).
    lat, lon:
        WGS-84 latitude / longitude in decimal degrees.
    alt:
        Altitude in metres (HAE).
    callsign:
        Human-readable callsign.
    heading:
        Course over ground in degrees (0-360).
    speed:
        Speed in metres per second.
    stale_seconds:
        Seconds until the event is considered stale.
    """
    now: datetime = _utc_now()
    stale: datetime = now + timedelta(seconds=stale_seconds)

    now_str: str = _format_iso(now)
    stale_str: str = _format_iso(stale)

    event = ET.Element("event", {
        "version": "2.0",
        "uid": uid,
        "type": cot_type,
        "how": "m-g",
        "time": now_str,
        "start": now_str,
        "stale": stale_str,
    })

    ET.SubElement(event, "point", {
        "lat": str(lat),
        "lon": str(lon),
        "hae": str(alt),
        "ce": "5.0",
        "le": "5.0",
    })

    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", {"callsign": callsign})
    ET.SubElement(detail, "track", {
        "course": str(heading),
        "speed": str(speed),
    })

    return ET.tostring(event, encoding="unicode", xml_declaration=False)


def build_cot_from_event(event: Any) -> str:
    """Convenience wrapper that accepts a *CoTEvent*-like object.

    The object must expose the attributes defined by
    :class:`CoTEventLike` (duck-typed so we avoid importing the
    Pydantic model from ``src/shared``).
    """
    return build_cot_xml(
        uid=event.uid,
        cot_type=event.cot_type,
        lat=event.lat,
        lon=event.lon,
        alt=event.alt_m,
        callsign=event.callsign,
        heading=event.heading,
        speed=event.speed_mps,
        stale_seconds=event.stale_seconds,
    )
