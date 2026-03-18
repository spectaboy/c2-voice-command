"""Behavioral rules-based IFF classification engine.

Classifies contacts on a threat score from 0.0 to 1.0 using weighted
behavioral indicators.  Deterministic, transparent, and tunable live.

Thresholds (from spec):
    >= 0.70  ->  Hostile
    0.40-0.69 -> Unknown (elevated)
    0.20-0.39 -> Unknown (low)
    < 0.20   ->  Neutral
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.iff.contact_tracker import Contact
from src.iff.geometry import (
    closing_speed,
    forward_bearing,
    haversine_distance,
    is_intercept_course,
    time_to_intercept,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOSTILE_THRESHOLD: float = 0.70
ELEVATED_THRESHOLD: float = 0.40
LOW_THRESHOLD: float = 0.20

# Proximity thresholds (meters)
CRITICAL_PROXIMITY_M: float = 500.0
WARNING_PROXIMITY_M: float = 2_000.0

# Loiter detection
LOITER_TIME_S: float = 300.0  # 5 minutes
LOITER_RADIUS_M: float = 200.0  # must stay within this radius to count

# Speed anomaly (ground contacts)
GROUND_SPEED_ANOMALY_MPS: float = 30.0  # 108 km/h

# Closing speed threshold for high-speed approach
HIGH_SPEED_CLOSE_MPS: float = 20.0

# Time-to-intercept threshold
TTI_CRITICAL_S: float = 60.0


@dataclass
class SensitiveArea:
    """A geofenced area that triggers elevated IFF scoring."""

    lat: float
    lon: float
    radius_m: float
    name: str = ""


# Default sensitive areas — Halifax Harbor demo
DEFAULT_SENSITIVE_AREAS: list[SensitiveArea] = [
    SensitiveArea(lat=44.6488, lon=-63.5752, radius_m=1_000.0, name="Halifax Harbor"),
    SensitiveArea(lat=44.6640, lon=-63.5680, radius_m=500.0, name="HMC Dockyard"),
]


# ---------------------------------------------------------------------------
# Classification logic
# ---------------------------------------------------------------------------


def _check_loitering(contact: Contact, area: SensitiveArea) -> bool:
    """Return True if the contact has loitered near *area* for > LOITER_TIME_S."""
    if len(contact.position_history) < 2:
        return False

    # Walk backward through history to find the earliest position still
    # within the loiter radius of the sensitive area.
    earliest_in_zone: Optional[float] = None
    for lat, lon, ts in contact.position_history:
        dist = haversine_distance(lat, lon, area.lat, area.lon)
        if dist <= area.radius_m + LOITER_RADIUS_M:
            if earliest_in_zone is None or ts < earliest_in_zone:
                earliest_in_zone = ts
        else:
            # Left the zone — reset
            earliest_in_zone = None

    if earliest_in_zone is None:
        return False

    latest_ts = contact.position_history[-1][2]
    return (latest_ts - earliest_in_zone) >= LOITER_TIME_S


def classify_contact(
    contact: Contact,
    friendlies: list[Contact],
    sensitive_areas: Optional[list[SensitiveArea]] = None,
) -> tuple[str, float, float, list[str]]:
    """Run all behavioral rules against *contact* and return classification.

    Returns:
        (affiliation, threat_score, confidence, indicators)
        affiliation: "h" | "u" | "n"  (never "f" — friendlies are pre-set)
        threat_score: 0.0–1.0 (capped; never 1.0 for auto-classification)
        confidence: 0.0–0.95 (auto can't reach 1.0 — human must confirm)
        indicators: list of human-readable strings
    """
    if sensitive_areas is None:
        sensitive_areas = DEFAULT_SENSITIVE_AREAS

    score: float = 0.0
    indicators: list[str] = []

    # ---- Rule 1: intercept course + critical proximity ----
    for friendly in friendlies:
        dist = haversine_distance(
            contact.lat, contact.lon, friendly.lat, friendly.lon
        )
        bearing_to_f = forward_bearing(
            contact.lat, contact.lon, friendly.lat, friendly.lon
        )

        on_intercept = is_intercept_course(contact.heading, bearing_to_f)
        cs = closing_speed(
            contact.lat, contact.lon, contact.heading, contact.speed,
            friendly.lat, friendly.lon, friendly.heading, friendly.speed,
        )

        if on_intercept and dist < CRITICAL_PROXIMITY_M and cs > 0:
            score += 0.40
            indicators.append(
                f"Intercept course toward {friendly.uid} at {dist:.0f}m "
                f"(closing {cs:.1f} m/s)"
            )
            break  # Worst-case already captured

        # ---- Rule 2: high-speed approach ----
        if cs > HIGH_SPEED_CLOSE_MPS and dist < WARNING_PROXIMITY_M:
            score += 0.30
            indicators.append(
                f"High-speed approach toward {friendly.uid}: "
                f"{cs:.1f} m/s closing at {dist:.0f}m"
            )
            break

    # ---- Rule 3: time-to-intercept ----
    for friendly in friendlies:
        dist = haversine_distance(
            contact.lat, contact.lon, friendly.lat, friendly.lon
        )
        cs = closing_speed(
            contact.lat, contact.lon, contact.heading, contact.speed,
            friendly.lat, friendly.lon, friendly.heading, friendly.speed,
        )
        tti = time_to_intercept(dist, cs)
        if tti is not None and tti < TTI_CRITICAL_S:
            score += 0.25
            indicators.append(
                f"Time-to-intercept {friendly.uid}: {tti:.0f}s"
            )
            break

    # ---- Rule 4 & 5: sensitive area proximity and loitering ----
    for area in sensitive_areas:
        dist_to_area = haversine_distance(
            contact.lat, contact.lon, area.lat, area.lon
        )
        if dist_to_area <= area.radius_m:
            score += 0.20
            indicators.append(
                f"Inside sensitive area '{area.name}' ({dist_to_area:.0f}m)"
            )

        if _check_loitering(contact, area):
            score += 0.20
            indicators.append(
                f"Loitering near '{area.name}' for >5 min"
            )

    # ---- Rule 6: anomalous speed for ground contacts ----
    if contact.domain == "ground" and contact.speed > GROUND_SPEED_ANOMALY_MPS:
        score += 0.15
        indicators.append(
            f"Anomalous ground speed: {contact.speed:.1f} m/s "
            f"({contact.speed * 3.6:.0f} km/h)"
        )

    # ---- Compute final classification ----
    score = min(score, 0.95)  # Auto-classification never reaches 1.0

    if score >= HOSTILE_THRESHOLD:
        affiliation = "h"
    elif score >= LOW_THRESHOLD:
        affiliation = "u"
    else:
        affiliation = "n"

    confidence = min(score, 0.95)

    return affiliation, score, confidence, indicators
