"""Pure-math geometry utilities for IFF classification.

All angles in degrees. All distances in meters. All speeds in m/s.
Uses WGS-84 mean Earth radius (6 371 000 m).
No external geo libraries — stdlib math only.
"""

from math import asin, atan2, cos, radians, sin, sqrt
from typing import Optional

_EARTH_RADIUS_M: float = 6_371_000.0


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in meters between two WGS-84 points."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return _EARTH_RADIUS_M * 2 * asin(sqrt(a))


def forward_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the initial (forward) bearing in degrees [0, 360) from point 1 to point 2."""
    rlat1, rlon1, rlat2, rlon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlon = rlon2 - rlon1
    x = sin(dlon) * cos(rlat2)
    y = cos(rlat1) * sin(rlat2) - sin(rlat1) * cos(rlat2) * cos(dlon)
    return atan2(x, y) * 180.0 / 3.141592653589793 % 360.0


def closing_speed(
    contact_lat: float,
    contact_lon: float,
    contact_heading_deg: float,
    contact_speed_mps: float,
    friendly_lat: float,
    friendly_lon: float,
    friendly_heading_deg: float,
    friendly_speed_mps: float,
) -> float:
    """Return the closing speed in m/s between two entities.

    Positive means they are approaching; negative means they are diverging.
    Each velocity vector is projected onto the line connecting the two entities.
    """
    # Bearing from contact -> friendly and from friendly -> contact.
    bearing_c_to_f = radians(forward_bearing(contact_lat, contact_lon, friendly_lat, friendly_lon))
    bearing_f_to_c = radians(forward_bearing(friendly_lat, friendly_lon, contact_lat, contact_lon))

    contact_heading_rad = radians(contact_heading_deg)
    friendly_heading_rad = radians(friendly_heading_deg)

    # Component of each velocity along the line toward the other entity.
    contact_closing = contact_speed_mps * cos(contact_heading_rad - bearing_c_to_f)
    friendly_closing = friendly_speed_mps * cos(friendly_heading_rad - bearing_f_to_c)

    return contact_closing + friendly_closing


def time_to_intercept(distance_m: float, closing_speed_mps: float) -> Optional[float]:
    """Return estimated seconds until intercept, or None if diverging/stationary."""
    if closing_speed_mps <= 0:
        return None
    return distance_m / closing_speed_mps


def is_intercept_course(
    contact_heading_deg: float,
    bearing_to_friendly_deg: float,
    threshold_deg: float = 25.0,
) -> bool:
    """Return True if the contact's heading is within *threshold_deg* of the bearing toward the friendly."""
    diff = (contact_heading_deg - bearing_to_friendly_deg + 180.0) % 360.0 - 180.0
    return abs(diff) <= threshold_deg
