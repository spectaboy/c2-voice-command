"""Pending confirmation store with TTL expiry."""

import time
import logging
from dataclasses import dataclass, field

from src.shared.schemas import MilitaryCommand

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30


@dataclass
class PendingConfirmation:
    command: MilitaryCommand
    readback: str
    created_at: float = field(default_factory=time.time)
    ttl: float = DEFAULT_TTL_SECONDS

    @property
    def expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl


class ConfirmationStore:
    """In-memory store for commands awaiting operator confirmation."""

    def __init__(self):
        self._pending: dict[str, PendingConfirmation] = {}

    def add(self, command: MilitaryCommand, readback: str) -> str:
        """Store a command pending confirmation. Returns command_id."""
        self._cleanup()
        self._pending[command.command_id] = PendingConfirmation(
            command=command, readback=readback
        )
        logger.info(f"Pending confirmation: {command.command_id} ({command.command_type})")
        return command.command_id

    def confirm(self, command_id: str) -> MilitaryCommand | None:
        """Confirm a pending command. Returns the command or None if expired/missing."""
        self._cleanup()
        pending = self._pending.pop(command_id, None)
        if pending is None:
            logger.warning(f"Confirmation not found or expired: {command_id}")
            return None
        logger.info(f"Confirmed: {command_id}")
        return pending.command

    def cancel(self, command_id: str) -> bool:
        """Cancel a pending command. Returns True if it was found."""
        self._cleanup()
        removed = self._pending.pop(command_id, None)
        if removed:
            logger.info(f"Cancelled: {command_id}")
        return removed is not None

    def list_pending(self) -> list[dict]:
        """Return all non-expired pending confirmations."""
        self._cleanup()
        return [
            {
                "command_id": cid,
                "command_type": p.command.command_type.value,
                "vehicle_callsign": p.command.vehicle_callsign,
                "readback": p.readback,
                "expires_in": round(p.ttl - (time.time() - p.created_at), 1),
            }
            for cid, p in self._pending.items()
        ]

    def _cleanup(self):
        """Remove expired entries."""
        expired = [cid for cid, p in self._pending.items() if p.expired]
        for cid in expired:
            logger.info(f"Expired confirmation: {cid}")
            del self._pending[cid]
