"""TCP client for sending Cursor-on-Target (CoT) XML events to FreeTAKServer.

Uses only stdlib ``asyncio`` for async networking and ``logging`` for
diagnostics.  If the server is unreachable the sender logs a warning and
continues -- it never crashes the calling service.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger: logging.Logger = logging.getLogger(__name__)


class CoTSender:
    """Asynchronous TCP sender for CoT XML events.

    Parameters
    ----------
    host:
        FreeTAKServer hostname or IP address.
    port:
        FreeTAKServer CoT input port (default ``8087``).
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8087) -> None:
        self._host: str = host
        self._port: int = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        """Whether the TCP connection is currently active."""
        return self._connected

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open an asynchronous TCP connection to FreeTAKServer.

        Raises
        ------
        OSError
            If the connection cannot be established (e.g. server not
            running).
        """
        logger.info("Connecting to FTS at %s:%d ...", self._host, self._port)
        self._reader, self._writer = await asyncio.open_connection(
            self._host, self._port,
        )
        self._connected = True
        logger.info("Connected to FTS at %s:%d", self._host, self._port)

    async def disconnect(self) -> None:
        """Gracefully close the TCP connection."""
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError as exc:
                logger.debug("Error while closing connection: %s", exc)
            finally:
                self._writer = None
                self._reader = None
                self._connected = False
                logger.info("Disconnected from FTS")

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_cot(self, xml_str: str) -> bool:
        """Send a CoT XML string over the TCP connection.

        The payload is encoded to UTF-8 bytes and terminated with a
        newline character before transmission.

        If the sender is not currently connected it will attempt a
        single reconnect before giving up for this message.

        Parameters
        ----------
        xml_str:
            A complete CoT ``<event>`` XML string.

        Returns
        -------
        bool
            ``True`` if the message was sent successfully, ``False``
            otherwise.
        """
        # Attempt reconnect if we're not connected.
        if not self._connected:
            if not await self._reconnect():
                return False

        try:
            data: bytes = (xml_str + "\n").encode("utf-8")
            self._writer.write(data)  # type: ignore[union-attr]
            await self._writer.drain()  # type: ignore[union-attr]
            logger.debug("Sent CoT event (%d bytes)", len(data))
            return True
        except OSError as exc:
            logger.warning("Send failed: %s — attempting reconnect", exc)
            self._connected = False

            # One retry after reconnect.
            if await self._reconnect():
                try:
                    data = (xml_str + "\n").encode("utf-8")
                    self._writer.write(data)  # type: ignore[union-attr]
                    await self._writer.drain()  # type: ignore[union-attr]
                    logger.debug("Sent CoT event on retry (%d bytes)", len(data))
                    return True
                except OSError as retry_exc:
                    logger.warning("Retry send also failed: %s", retry_exc)
                    self._connected = False

            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _reconnect(self) -> bool:
        """Try to re-establish the TCP connection (single attempt).

        Returns
        -------
        bool
            ``True`` if the reconnection succeeded, ``False`` otherwise.
        """
        try:
            await self.connect()
            return True
        except OSError as exc:
            logger.warning(
                "Could not reconnect to FTS at %s:%d — %s",
                self._host,
                self._port,
                exc,
            )
            self._connected = False
            return False
