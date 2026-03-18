"""Simulated "unknown" contacts for IFF demo purposes.

These are **not** SITL vehicles -- they are fake CoT positions that move on
predefined waypoint paths so that the IFF rules engine can be exercised
without live hardware.

Demo location: Halifax Harbor (44.6488, -63.5752).

Default sensitive areas
-----------------------
* Halifax Harbor -- (44.6488, -63.5752, 1 000 m radius)
* HMC Dockyard  -- (44.6640, -63.5680, 500 m radius)

Three canned contacts are provided by :func:`get_default_contacts`:

* **UNKNOWN-01** "The Interceptor" -- drives north toward a friendly asset
  and should eventually be classified hostile.
* **UNKNOWN-02** "The Loiterer" -- orbits inside HMC Dockyard and should
  trigger the loitering-in-sensitive-area rule.
* **UNKNOWN-03** "The Passerby" -- moves away from everything and should
  stay neutral.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

from src.iff.contact_tracker import ContactTracker
from src.iff.geometry import forward_bearing, haversine_distance
from src.tak.cot_builder import build_cot_xml
from src.tak.cot_sender import CoTSender
from src.tak.cot_type_manager import get_cot_type

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EARTH_RADIUS_M: float = 6_371_000.0

# Halifax Harbor demo centre
_HARBOR_LAT: float = 44.6488
_HARBOR_LON: float = -63.5752

# HMC Dockyard demo centre
_DOCKYARD_LAT: float = 44.6640
_DOCKYARD_LON: float = -63.5680


# ---------------------------------------------------------------------------
# Geometry helper -- inverse haversine (destination point)
# ---------------------------------------------------------------------------

def destination_point(
    lat: float,
    lon: float,
    bearing_deg: float,
    distance_m: float,
) -> tuple[float, float]:
    """Return the (lat, lon) reached by travelling *distance_m* metres from
    (*lat*, *lon*) along *bearing_deg* (degrees clockwise from north).

    Uses the inverse haversine formula on a spherical Earth model
    (WGS-84 mean radius = 6 371 000 m).
    """
    rlat = math.radians(lat)
    rlon = math.radians(lon)
    rbearing = math.radians(bearing_deg)
    angular_distance = distance_m / _EARTH_RADIUS_M

    new_lat = math.asin(
        math.sin(rlat) * math.cos(angular_distance)
        + math.cos(rlat) * math.sin(angular_distance) * math.cos(rbearing)
    )
    new_lon = rlon + math.atan2(
        math.sin(rbearing) * math.sin(angular_distance) * math.cos(rlat),
        math.cos(angular_distance) - math.sin(rlat) * math.sin(new_lat),
    )

    return math.degrees(new_lat), math.degrees(new_lon)


# ---------------------------------------------------------------------------
# SimulatedContact
# ---------------------------------------------------------------------------

@dataclass
class SimulatedContact:
    """A single fake contact that moves along a waypoint path.

    Parameters
    ----------
    uid:
        Unique identifier (e.g. ``"UNKNOWN-01"``).
    domain:
        One of ``"ground"``, ``"air"``, or ``"maritime"``.
    waypoints:
        Ordered list of ``(lat, lon)`` positions defining the route.
    speed_mps:
        Travel speed in metres per second.
    """

    uid: str
    domain: str
    waypoints: list[tuple[float, float]]
    speed_mps: float

    # Pre-computed segment data (populated by __post_init__).
    _segment_bearings: list[float] = field(
        default_factory=list, init=False, repr=False
    )
    _segment_distances: list[float] = field(
        default_factory=list, init=False, repr=False
    )
    _total_path_distance: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        """Pre-compute bearings and distances between consecutive waypoints."""
        self._recompute_segments()

    def _recompute_segments(self) -> None:
        bearings: list[float] = []
        distances: list[float] = []
        for i in range(len(self.waypoints) - 1):
            lat1, lon1 = self.waypoints[i]
            lat2, lon2 = self.waypoints[i + 1]
            bearings.append(forward_bearing(lat1, lon1, lat2, lon2))
            distances.append(haversine_distance(lat1, lon1, lat2, lon2))
        self._segment_bearings = bearings
        self._segment_distances = distances
        self._total_path_distance = sum(distances)

    def current_position(self, elapsed_s: float) -> tuple[float, float, float]:
        """Return ``(lat, lon, heading)`` after *elapsed_s* seconds of travel.

        The contact moves at constant :attr:`speed_mps` along the waypoint
        path.  When the end of the waypoint list is reached the contact
        wraps back to the first waypoint and continues (infinite loop).
        """
        if not self._segment_distances:
            # Only one waypoint -- stationary contact.
            lat, lon = self.waypoints[0]
            return lat, lon, 0.0

        # Total distance covered (modulo total path length for looping).
        distance_covered = self.speed_mps * elapsed_s
        if self._total_path_distance > 0:
            distance_covered = distance_covered % self._total_path_distance

        # Walk through segments until we find the one we're on.
        for i, seg_dist in enumerate(self._segment_distances):
            if distance_covered <= seg_dist:
                lat_start, lon_start = self.waypoints[i]
                bearing = self._segment_bearings[i]
                lat, lon = destination_point(
                    lat_start, lon_start, bearing, distance_covered
                )
                return lat, lon, bearing
            distance_covered -= seg_dist

        # Floating-point edge case -- snap to the last waypoint.
        lat, lon = self.waypoints[-1]
        heading = self._segment_bearings[-1] if self._segment_bearings else 0.0
        return lat, lon, heading


# ---------------------------------------------------------------------------
# Default contacts factory
# ---------------------------------------------------------------------------

def _build_loiter_waypoints(
    centre_lat: float,
    centre_lon: float,
    radius_m: float,
    num_points: int = 12,
) -> list[tuple[float, float]]:
    """Generate a closed circular waypoint path of *num_points* evenly-spaced
    points around (*centre_lat*, *centre_lon*) at *radius_m* metres.

    The last waypoint is identical to the first so the loop closes
    seamlessly when the contact wraps.
    """
    waypoints: list[tuple[float, float]] = []
    for i in range(num_points):
        bearing = (360.0 / num_points) * i
        waypoints.append(
            destination_point(centre_lat, centre_lon, bearing, radius_m)
        )
    # Close the loop.
    waypoints.append(waypoints[0])
    return waypoints


def get_default_contacts() -> list[SimulatedContact]:
    """Create the three canned demo contacts.

    * ``UNKNOWN-01`` -- "The Interceptor" (ground, 15 m/s, heads north
      toward Halifax Harbor friendly position).
    * ``UNKNOWN-02`` -- "The Loiterer" (ground, 3 m/s, circles inside
      HMC Dockyard sensitive area).
    * ``UNKNOWN-03`` -- "The Passerby" (ground, 12 m/s, moves east and
      away from all assets).
    """
    # ---- UNKNOWN-01: The Interceptor ----
    # Starts ~3 km south of Halifax Harbor, drives north toward the
    # friendly position assumed to be at (_HARBOR_LAT, _HARBOR_LON).
    interceptor_start = destination_point(_HARBOR_LAT, _HARBOR_LON, 180.0, 3000.0)
    interceptor_mid = destination_point(_HARBOR_LAT, _HARBOR_LON, 180.0, 1500.0)
    interceptor_end = (_HARBOR_LAT, _HARBOR_LON)

    interceptor = SimulatedContact(
        uid="UNKNOWN-01",
        domain="ground",
        waypoints=[interceptor_start, interceptor_mid, interceptor_end],
        speed_mps=15.0,
    )

    # ---- UNKNOWN-02: The Loiterer ----
    # Slow circular path within 400 m of HMC Dockyard.
    loiter_wps = _build_loiter_waypoints(
        centre_lat=_DOCKYARD_LAT,
        centre_lon=_DOCKYARD_LON,
        radius_m=400.0,
        num_points=12,
    )

    loiterer = SimulatedContact(
        uid="UNKNOWN-02",
        domain="ground",
        waypoints=loiter_wps,
        speed_mps=3.0,
    )

    # ---- UNKNOWN-03: The Passerby ----
    # Starts ~2 km east of the harbor and moves further east.
    passerby_start = destination_point(_HARBOR_LAT, _HARBOR_LON, 90.0, 2000.0)
    passerby_mid = destination_point(_HARBOR_LAT, _HARBOR_LON, 90.0, 4000.0)
    passerby_end = destination_point(_HARBOR_LAT, _HARBOR_LON, 90.0, 7000.0)

    passerby = SimulatedContact(
        uid="UNKNOWN-03",
        domain="ground",
        waypoints=[passerby_start, passerby_mid, passerby_end],
        speed_mps=12.0,
    )

    return [interceptor, loiterer, passerby]


# ---------------------------------------------------------------------------
# ContactSimulator -- async run-loop
# ---------------------------------------------------------------------------

class ContactSimulator:
    """Drives simulated contacts through the IFF pipeline at a fixed cadence.

    Each tick:
    1. Computes the current position for every :class:`SimulatedContact`.
    2. Upserts kinematic data into the :class:`ContactTracker`.
    3. Builds a CoT XML event (unknown affiliation) and sends it via the
       :class:`CoTSender`.
    """

    def __init__(
        self,
        contacts: Optional[list[SimulatedContact]] = None,
    ) -> None:
        self._contacts: list[SimulatedContact] = (
            contacts if contacts is not None else get_default_contacts()
        )
        self._start_time: Optional[float] = None

    @property
    def contacts(self) -> list[SimulatedContact]:
        """The list of simulated contacts managed by this simulator."""
        return list(self._contacts)

    async def run(
        self,
        tracker: ContactTracker,
        cot_sender: CoTSender,
        interval_s: float = 1.0,
    ) -> None:
        """Run the simulation loop forever.

        Parameters
        ----------
        tracker:
            The :class:`ContactTracker` instance to upsert kinematic data
            into.
        cot_sender:
            The :class:`CoTSender` used to publish CoT XML events to
            FreeTAKServer.
        interval_s:
            Seconds between simulation ticks (default ``1.0``).
        """
        self._start_time = time.monotonic()
        logger.info(
            "ContactSimulator started with %d contacts (interval=%.1fs)",
            len(self._contacts),
            interval_s,
        )

        while True:
            elapsed = time.monotonic() - self._start_time

            for contact in self._contacts:
                try:
                    lat, lon, heading = contact.current_position(elapsed)

                    # Upsert into the tracker.
                    await tracker.update_contact(
                        uid=contact.uid,
                        lat=lat,
                        lon=lon,
                        alt=0.0,
                        heading=heading,
                        speed=contact.speed_mps,
                        domain=contact.domain,
                    )

                    # Build and send a CoT event with "unknown" affiliation.
                    cot_type = get_cot_type(contact.domain, "u")
                    xml = build_cot_xml(
                        uid=contact.uid,
                        cot_type=cot_type,
                        lat=lat,
                        lon=lon,
                        alt=0.0,
                        callsign=contact.uid,
                        heading=heading,
                        speed=contact.speed_mps,
                        stale_seconds=int(interval_s * 3),
                    )
                    await cot_sender.send_cot(xml)

                    logger.debug(
                        "%s  lat=%.6f  lon=%.6f  hdg=%.1f  spd=%.1f",
                        contact.uid,
                        lat,
                        lon,
                        heading,
                        contact.speed_mps,
                    )
                except Exception:
                    logger.exception(
                        "Error updating simulated contact %s", contact.uid
                    )

            await asyncio.sleep(interval_s)
