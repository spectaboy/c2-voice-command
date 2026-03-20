from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional, List
from datetime import datetime
from uuid import uuid4


class Domain(str, Enum):
    AIR = "air"
    GROUND = "ground"
    MARITIME = "maritime"


class Affiliation(str, Enum):
    FRIENDLY = "f"
    HOSTILE = "h"
    UNKNOWN = "u"
    NEUTRAL = "n"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CommandType(str, Enum):
    MOVE = "move"
    RTB = "rtb"
    LOITER = "loiter"
    PATROL = "patrol"
    OVERWATCH = "overwatch"
    ENGAGE = "engage"
    CLASSIFY = "classify"
    STATUS = "status"
    TAKEOFF = "takeoff"
    LAND = "land"


class Location(BaseModel):
    lat: float
    lon: float
    alt_m: float = 0.0
    grid_ref: Optional[str] = None


class MilitaryCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid4())[:8])
    command_type: CommandType
    vehicle_callsign: str
    domain: Domain
    location: Optional[Location] = None
    parameters: dict = {}
    raw_transcript: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    requires_confirmation: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VehicleStatus(BaseModel):
    uid: str
    callsign: str
    domain: Domain
    affiliation: Affiliation
    lat: float
    lon: float
    alt_m: float
    heading: float
    speed_mps: float
    battery_pct: float = 100.0
    mode: str = "GUIDED"
    armed: bool = False


class IFFAssessment(BaseModel):
    uid: str
    affiliation: Affiliation
    confidence: float
    threat_score: float
    indicators: List[str]
    timestamp: str


class CoTEvent(BaseModel):
    uid: str
    cot_type: str
    lat: float
    lon: float
    alt_m: float
    callsign: str
    heading: float = 0.0
    speed_mps: float = 0.0
    stale_seconds: int = 30


class WSMessage(BaseModel):
    type: str
    payload: dict
    timestamp: datetime = Field(default_factory=datetime.utcnow)
