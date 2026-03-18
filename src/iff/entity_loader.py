"""Load an Entity List JSON file and seed the IFF ContactTracker.

Expected JSON structure::

    {
      "entities": [
        {
          "uid": "SITL-UAV-1",
          "callsign": "UAV-1",       // optional
          "affiliation": "f",         // "f" | "h" | "u" | "n"
          "domain": "air",            // "air" | "ground" | "maritime"
          "lat": 44.6488,
          "lon": -63.5752,
          "alt": 0.0                  // optional, defaults to 0.0
        }
      ]
    }

Usage::

    from src.iff.entity_loader import load_entity_list
    count = await load_entity_list(tracker, "data/entity_list.json")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.iff.contact_tracker import ContactTracker

logger: logging.Logger = logging.getLogger(__name__)

_VALID_AFFILIATIONS = {"f", "h", "u", "n"}
_VALID_DOMAINS = {"air", "ground", "maritime"}


def _parse_entities(raw: Any) -> list[dict]:
    """Extract and validate the entity list from parsed JSON.

    Accepts either ``{"entities": [...]}`` or a bare list ``[...]``.
    Skips entries that are missing required fields rather than failing
    the entire load.
    """
    if isinstance(raw, dict):
        entries = raw.get("entities", [])
    elif isinstance(raw, list):
        entries = raw
    else:
        logger.warning("Entity list JSON root is neither dict nor list")
        return []

    valid: list[dict] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            logger.warning("Entity %d is not a dict — skipping", i)
            continue
        uid = entry.get("uid")
        if not uid:
            logger.warning("Entity %d missing 'uid' — skipping", i)
            continue
        affiliation = entry.get("affiliation", "u")
        if affiliation not in _VALID_AFFILIATIONS:
            logger.warning(
                "Entity %s has invalid affiliation '%s' — defaulting to 'u'",
                uid, affiliation,
            )
            affiliation = "u"
        domain = entry.get("domain", "ground")
        if domain not in _VALID_DOMAINS:
            domain = "ground"
        valid.append({
            "uid": uid,
            "callsign": entry.get("callsign", uid),
            "affiliation": affiliation,
            "domain": domain,
            "lat": float(entry.get("lat", 0.0)),
            "lon": float(entry.get("lon", 0.0)),
            "alt": float(entry.get("alt", 0.0)),
        })
    return valid


async def load_entity_list(
    tracker: ContactTracker,
    path: str | Path,
) -> int:
    """Load entities from *path* into *tracker*.

    Returns the number of entities successfully seeded.
    """
    path = Path(path)
    if not path.is_file():
        logger.warning("Entity list file not found: %s", path)
        return 0

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read entity list %s: %s", path, exc)
        return 0

    entities = _parse_entities(raw)
    if not entities:
        logger.warning("No valid entities found in %s", path)
        return 0

    count = 0
    for ent in entities:
        # Upsert the contact with initial position
        await tracker.update_contact(
            uid=ent["uid"],
            lat=ent["lat"],
            lon=ent["lon"],
            alt=ent["alt"],
            heading=0.0,
            speed=0.0,
            domain=ent["domain"],
        )
        # Set initial classification
        affiliation = ent["affiliation"]
        if affiliation == "f":
            threat_score = 0.0
            confidence = 1.0
            indicators = ["Friendly — entity list"]
        elif affiliation == "h":
            threat_score = 1.0
            confidence = 1.0
            indicators = ["Hostile — entity list"]
        elif affiliation == "n":
            threat_score = 0.0
            confidence = 0.5
            indicators = ["Neutral — entity list"]
        else:
            threat_score = 0.5
            confidence = 0.0
            indicators = ["Unknown — entity list"]

        await tracker.set_classification(
            uid=ent["uid"],
            affiliation=affiliation,
            threat_score=threat_score,
            confidence=confidence,
            indicators=indicators,
        )
        count += 1

    logger.info("Loaded %d entities from %s", count, path)
    return count
