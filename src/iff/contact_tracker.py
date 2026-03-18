"""Stateful contact tracking for the IFF engine.

Maintains the current state of all tracked contacts (friendly vehicles,
unknown entities, and hostile entities) with thread-safe async access.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

_POSITION_HISTORY_CAP = 300


@dataclass
class Contact:
    """A single tracked contact."""

    uid: str
    lat: float
    lon: float
    alt: float  # meters
    heading: float  # degrees
    speed: float  # m/s
    affiliation: str = "u"  # "f" | "h" | "u" | "n"
    threat_score: float = 0.0  # 0.0 – 1.0
    confidence: float = 0.0  # 0.0 – 1.0
    indicators: list[str] = field(default_factory=list)
    domain: str = "ground"  # "air" | "ground" | "maritime"
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    position_history: list[tuple[float, float, float]] = field(
        default_factory=list
    )  # (lat, lon, timestamp), capped at 300


class ContactTracker:
    """Thread-safe registry of all contacts known to the IFF engine."""

    def __init__(self) -> None:
        self._contacts: dict[str, Contact] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    async def update_contact(
        self,
        uid: str,
        lat: float,
        lon: float,
        alt: float,
        heading: float,
        speed: float,
        domain: str = "ground",
    ) -> Contact:
        """Upsert a contact with the latest kinematic data.

        If the contact does not yet exist it is created with *first_seen* set
        to the current time.  *last_seen* is always refreshed, and the new
        position is appended to *position_history* (capped at 300 entries).
        """
        now = time.time()
        async with self._lock:
            contact = self._contacts.get(uid)
            if contact is None:
                contact = Contact(
                    uid=uid,
                    lat=lat,
                    lon=lon,
                    alt=alt,
                    heading=heading,
                    speed=speed,
                    domain=domain,
                    first_seen=now,
                    last_seen=now,
                    position_history=[(lat, lon, now)],
                )
                self._contacts[uid] = contact
            else:
                contact.lat = lat
                contact.lon = lon
                contact.alt = alt
                contact.heading = heading
                contact.speed = speed
                contact.domain = domain
                contact.last_seen = now

                contact.position_history.append((lat, lon, now))
                if len(contact.position_history) > _POSITION_HISTORY_CAP:
                    contact.position_history = contact.position_history[
                        -_POSITION_HISTORY_CAP:
                    ]

            return contact

    async def get_contact(self, uid: str) -> Optional[Contact]:
        """Return the contact with the given *uid*, or ``None``."""
        async with self._lock:
            return self._contacts.get(uid)

    async def get_all_contacts(self) -> list[Contact]:
        """Return a list of every tracked contact."""
        async with self._lock:
            return list(self._contacts.values())

    async def set_classification(
        self,
        uid: str,
        affiliation: str,
        threat_score: float,
        confidence: float,
        indicators: list[str],
    ) -> Optional[Contact]:
        """Update the classification fields of an existing contact.

        Returns the updated :class:`Contact`, or ``None`` if *uid* is not
        currently tracked.
        """
        async with self._lock:
            contact = self._contacts.get(uid)
            if contact is None:
                return None
            contact.affiliation = affiliation
            contact.threat_score = threat_score
            contact.confidence = confidence
            contact.indicators = indicators
            return contact

    async def remove_stale(self, timeout_s: float = 120) -> list[str]:
        """Remove contacts that have not been updated within *timeout_s* seconds.

        Returns a list of UIDs that were removed.
        """
        now = time.time()
        async with self._lock:
            stale_uids: list[str] = [
                uid
                for uid, contact in self._contacts.items()
                if (now - contact.last_seen) > timeout_s
            ]
            for uid in stale_uids:
                del self._contacts[uid]
            return stale_uids

    async def get_friendlies(self) -> list[Contact]:
        """Return all contacts whose affiliation is ``"f"`` (friendly)."""
        async with self._lock:
            return [
                c for c in self._contacts.values() if c.affiliation == "f"
            ]
