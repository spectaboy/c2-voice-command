"""Append-only audit trail for IFF classification changes.

Every time a contact's classification changes (automatically or manually),
it gets logged here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional


@dataclass
class AuditEntry:
    """A single record of an IFF classification change."""

    timestamp: str
    uid: str
    previous_affiliation: str
    new_affiliation: str
    confidence: float
    threat_score: float
    indicators: list[str]
    source: str


class AuditTrail:
    """Append-only log of IFF classification changes.

    Parameters
    ----------
    max_entries:
        Maximum number of entries to retain.  When the limit is exceeded the
        oldest entries are dropped first.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries: int = max_entries

    def add_entry(
        self,
        uid: str,
        previous_affiliation: str,
        new_affiliation: str,
        confidence: float,
        threat_score: float,
        indicators: list[str],
        source: str = "auto",
    ) -> AuditEntry:
        """Create and store a new audit entry with the current UTC timestamp.

        If the trail exceeds *max_entries* after the append, the oldest
        entries are dropped.
        """
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            uid=uid,
            previous_affiliation=previous_affiliation,
            new_affiliation=new_affiliation,
            confidence=confidence,
            threat_score=threat_score,
            indicators=list(indicators),
            source=source,
        )
        self._entries.append(entry)

        # Trim oldest entries when over the limit.
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        return entry

    def get_recent(self, count: int = 50) -> list[AuditEntry]:
        """Return the last *count* entries, newest first."""
        return list(reversed(self._entries[-count:]))

    def get_for_contact(self, uid: str) -> list[AuditEntry]:
        """Return all entries for a specific contact UID, newest first."""
        return list(reversed([e for e in self._entries if e.uid == uid]))

    def to_dicts(
        self, entries: Optional[list[AuditEntry]] = None
    ) -> list[dict]:
        """Convert entries to a list of plain dicts for JSON serialization.

        If *entries* is ``None``, all stored entries are converted.
        """
        target = entries if entries is not None else self._entries
        return [asdict(e) for e in target]

    def clear(self) -> None:
        """Remove all entries from the audit trail."""
        self._entries.clear()
