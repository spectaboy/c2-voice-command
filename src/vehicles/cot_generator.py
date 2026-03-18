import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

from src.shared.schemas import VehicleStatus
from src.shared.constants import COT_TYPES


class CoTGenerator:
    """Converts VehicleStatus into Cursor-on-Target XML events."""

    def __init__(self):
        # Overrides: uid -> affiliation. Used when IFF engine reclassifies.
        self._affiliation_overrides: dict[str, str] = {}

    def update_affiliation(self, uid: str, new_affiliation: str) -> None:
        """Override a vehicle's affiliation for CoT type string generation."""
        self._affiliation_overrides[uid] = new_affiliation

    def generate_cot_event(self, status: VehicleStatus) -> str:
        """Build a CoT XML string from a VehicleStatus."""
        now = datetime.now(timezone.utc)
        stale = now + timedelta(seconds=30)

        # Determine affiliation (check overrides first)
        affiliation = self._affiliation_overrides.get(
            status.uid, status.affiliation.value
        )
        cot_type = COT_TYPES.get(
            (status.domain.value, affiliation),
            f"a-{affiliation}-X",  # fallback
        )

        time_str = _fmt_time(now)
        stale_str = _fmt_time(stale)

        event = ET.Element("event")
        event.set("version", "2.0")
        event.set("uid", status.uid)
        event.set("type", cot_type)
        event.set("how", "m-g")
        event.set("time", time_str)
        event.set("start", time_str)
        event.set("stale", stale_str)

        point = ET.SubElement(event, "point")
        point.set("lat", f"{status.lat:.7f}")
        point.set("lon", f"{status.lon:.7f}")
        point.set("hae", f"{status.alt_m:.1f}")
        point.set("ce", "5.0")
        point.set("le", "5.0")

        detail = ET.SubElement(event, "detail")

        contact = ET.SubElement(detail, "contact")
        contact.set("callsign", status.callsign)

        track = ET.SubElement(detail, "track")
        track.set("course", f"{status.heading:.1f}")
        track.set("speed", f"{status.speed_mps:.1f}")

        return ET.tostring(event, encoding="unicode")


def _fmt_time(dt: datetime) -> str:
    """Format datetime as ISO 8601 UTC with Z suffix."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
