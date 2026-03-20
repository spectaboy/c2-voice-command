import asyncio
import logging
import time

logger = logging.getLogger(__name__)

RECONNECT_DELAY = 3.0
RECONNECT_BACKOFF_MAX = 30.0  # Max delay between reconnect attempts


class CoTSender:
    """Sends CoT XML events to FreeTAKServer over TCP."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8087):
        self.host = host
        self.port = port
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._last_reconnect_attempt = 0.0
        self._reconnect_delay = RECONNECT_DELAY

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Open TCP connection to FreeTAKServer."""
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            self._connected = True
            logger.info(f"CoTSender connected to {self.host}:{self.port}")
        except (ConnectionRefusedError, OSError) as e:
            self._connected = False
            logger.debug(f"CoTSender: FTS not available ({e})")

    async def send(self, cot_xml: str) -> bool:
        """Send a CoT XML event. Returns True if sent successfully."""
        if not self._connected or self._writer is None:
            await self._reconnect()
            if not self._connected:
                return False

        try:
            data = (cot_xml + "\n").encode("utf-8")
            self._writer.write(data)
            await self._writer.drain()
            return True
        except (ConnectionResetError, BrokenPipeError, OSError) as e:
            logger.debug(f"CoTSender send failed: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> None:
        """Close the TCP connection."""
        self._connected = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        logger.info("CoTSender disconnected")

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff (max 30s)."""
        now = time.time()
        # Skip if we attempted too recently
        if now - self._last_reconnect_attempt < self._reconnect_delay:
            return
        self._last_reconnect_attempt = now
        logger.debug("CoTSender attempting reconnect (backoff=%.0fs)...", self._reconnect_delay)
        await self.disconnect()
        await asyncio.sleep(self._reconnect_delay)
        await self.connect()
        if self._connected:
            self._reconnect_delay = RECONNECT_DELAY  # Reset on success
        else:
            self._reconnect_delay = min(self._reconnect_delay * 2, RECONNECT_BACKOFF_MAX)
