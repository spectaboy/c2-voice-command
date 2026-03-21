"""Tests for Phase 1 bug fixes: ENGAGE handler, PATROL waypoints, LOITER navigation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.shared.schemas import (
    MilitaryCommand, CommandType, Domain, Location, RiskLevel,
    VehicleStatus, Affiliation,
)
from src.vehicles.vehicle_manager import VehicleManager
from src.nlu.parser import _tool_result_to_command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Get actual callsigns from the fleet
from src.shared.battlespace import get_active_vehicles
_FLEET = get_active_vehicles()
_CALLSIGNS = list(_FLEET.keys())
CS1 = _CALLSIGNS[0]  # First vehicle (e.g., "Alpha")
CS2 = _CALLSIGNS[1] if len(_CALLSIGNS) > 1 else CS1  # Second vehicle


def _make_cmd(
    cmd_type=CommandType.MOVE,
    callsign=None,
    domain=Domain.AIR,
    lat=44.65,
    lon=-63.57,
    alt_m=100.0,
    parameters=None,
    location=True,
) -> MilitaryCommand:
    if callsign is None:
        callsign = CS1
    loc = Location(lat=lat, lon=lon, alt_m=alt_m) if location else None
    return MilitaryCommand(
        command_type=cmd_type,
        vehicle_callsign=callsign,
        domain=domain,
        location=loc,
        parameters=parameters or {},
    )


def _mock_status(callsign="Alpha") -> VehicleStatus:
    return VehicleStatus(
        uid=f"SITL-{callsign}",
        callsign=callsign,
        domain=Domain.AIR,
        affiliation=Affiliation.FRIENDLY,
        lat=44.65,
        lon=-63.57,
        alt_m=100.0,
        heading=45.0,
        speed_mps=15.0,
    )


class TestVehicleManagerSetup:
    """Base class that sets up a VehicleManager with mocked clients."""

    def setup_method(self):
        self.mgr = VehicleManager()
        for client in self.mgr._clients.values():
            client._connected = True
            client._last_heartbeat = 9999999999.0
            client.move_to = AsyncMock(return_value=True)
            client.rtb = AsyncMock(return_value=True)
            client.set_mode = AsyncMock(return_value=True)
            client.takeoff = AsyncMock(return_value=True)
            client.land = AsyncMock(return_value=True)
            client.get_status = MagicMock(return_value=_mock_status(client.callsign))


# ---------------------------------------------------------------------------
# Bug 1: ENGAGE handler
# ---------------------------------------------------------------------------

class TestEngageHandler(TestVehicleManagerSetup):

    @pytest.mark.asyncio
    async def test_engage_with_location(self):
        """ENGAGE with a target location should move_to + set CIRCLE mode."""
        cmd = _make_cmd(
            CommandType.ENGAGE, CS1,
            lat=44.66, lon=-63.58, alt_m=50.0,
            parameters={"target_uid": "HOSTILE-01"},
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "engage"
        assert result["target_uid"] == "HOSTILE-01"
        self.mgr._clients[CS1].move_to.assert_awaited_once_with(44.66, -63.58, 50.0)
        self.mgr._clients[CS1].set_mode.assert_awaited_once_with("CIRCLE")

    @pytest.mark.asyncio
    async def test_engage_without_location(self):
        """ENGAGE without location should still set CIRCLE mode (orbit in place)."""
        cmd = _make_cmd(
            CommandType.ENGAGE, CS1,
            parameters={"target_uid": "HOSTILE-02"},
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "engage"
        self.mgr._clients[CS1].move_to.assert_not_awaited()
        self.mgr._clients[CS1].set_mode.assert_awaited_once_with("CIRCLE")

    @pytest.mark.asyncio
    async def test_engage_no_longer_unsupported(self):
        """ENGAGE must NOT fall through to the default 'unsupported' case."""
        cmd = _make_cmd(
            CommandType.ENGAGE, CS1,
            parameters={"target_uid": "HOSTILE-01"},
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert "Unsupported" not in result.get("error", "")

    @pytest.mark.asyncio
    async def test_engage_default_altitude(self):
        """ENGAGE with alt_m=0 should default to 50m."""
        cmd = _make_cmd(
            CommandType.ENGAGE, CS1,
            lat=44.66, lon=-63.58, alt_m=0.0,
            parameters={"target_uid": "HOSTILE-01"},
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        self.mgr._clients[CS1].move_to.assert_awaited_once_with(44.66, -63.58, 50.0)


# ---------------------------------------------------------------------------
# Bug 2: PATROL waypoints
# ---------------------------------------------------------------------------

class TestPatrolWaypoints(TestVehicleManagerSetup):

    @pytest.mark.asyncio
    async def test_patrol_with_waypoints_in_parameters(self):
        """PATROL with waypoints in parameters should move to first waypoint."""
        waypoints = [
            {"lat": 44.66, "lon": -63.58, "alt_m": 100.0},
            {"lat": 44.67, "lon": -63.59, "alt_m": 100.0},
        ]
        cmd = _make_cmd(
            CommandType.PATROL, CS1,
            parameters={"waypoints": waypoints},
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "patrol"
        self.mgr._clients[CS1].move_to.assert_awaited_once_with(44.66, -63.58, 100.0)

    @pytest.mark.asyncio
    async def test_patrol_with_location_fallback(self):
        """PATROL with cmd.location (no waypoints) should still work."""
        cmd = _make_cmd(
            CommandType.PATROL, CS1,
            lat=44.66, lon=-63.58, alt_m=100.0,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        self.mgr._clients[CS1].move_to.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_patrol_without_anything(self):
        """PATROL with no waypoints and no location should succeed (no movement)."""
        cmd = _make_cmd(
            CommandType.PATROL, CS1,
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        self.mgr._clients[CS1].move_to.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_patrol_waypoint_default_altitude_copter(self):
        """PATROL waypoint without alt_m should default to 100m for copters."""
        waypoints = [{"lat": 44.66, "lon": -63.58}]  # no alt_m
        cmd = _make_cmd(
            CommandType.PATROL, CS1,
            parameters={"waypoints": waypoints},
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        self.mgr._clients[CS1].move_to.assert_awaited_once_with(44.66, -63.58, 100.0)


# ---------------------------------------------------------------------------
# Bug 2 (parser side): patrol_route tool → MilitaryCommand conversion
# ---------------------------------------------------------------------------

class TestPatrolParserConversion:

    @patch("src.nlu.parser._resolve_callsign", return_value=("Alpha", Domain.AIR))
    def test_patrol_route_extracts_first_waypoint(self, mock_resolve):
        """patrol_route tool call should produce a MilitaryCommand with location from first waypoint."""
        tool_input = {
            "callsign": "Alpha",
            "waypoints": [
                {"lat": 44.66, "lon": -63.58, "alt_m": 80.0},
                {"lat": 44.67, "lon": -63.59, "alt_m": 80.0},
            ],
        }
        cmd = _tool_result_to_command("patrol_route", tool_input, "patrol between A and B")
        assert cmd.command_type == CommandType.PATROL
        assert cmd.location is not None
        assert cmd.location.lat == 44.66
        assert cmd.location.lon == -63.58
        assert cmd.location.alt_m == 80.0
        # Waypoints should also be in parameters
        assert "waypoints" in cmd.parameters
        assert len(cmd.parameters["waypoints"]) == 2

    @patch("src.nlu.parser._resolve_callsign", return_value=("Alpha", Domain.AIR))
    def test_patrol_route_default_alt(self, mock_resolve):
        """Patrol waypoint without alt_m should default based on domain."""
        tool_input = {
            "callsign": "Alpha",
            "waypoints": [{"lat": 44.66, "lon": -63.58}],
        }
        cmd = _tool_result_to_command("patrol_route", tool_input, "patrol area")
        assert cmd.location is not None
        assert cmd.location.alt_m == 100.0  # AIR domain default


# ---------------------------------------------------------------------------
# Bug 3: LOITER navigation
# ---------------------------------------------------------------------------

class TestLoiterNavigation(TestVehicleManagerSetup):

    @pytest.mark.asyncio
    async def test_loiter_with_location_navigates_first(self):
        """LOITER with a location should move_to THEN set_mode LOITER."""
        cmd = _make_cmd(
            CommandType.LOITER, CS2,
            lat=44.66, lon=-63.58, alt_m=80.0,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "loiter"
        self.mgr._clients[CS2].move_to.assert_awaited_once_with(44.66, -63.58, 80.0)
        self.mgr._clients[CS2].set_mode.assert_awaited_once_with("LOITER")

    @pytest.mark.asyncio
    async def test_loiter_without_location_just_sets_mode(self):
        """LOITER without location should just set mode (hold current position)."""
        cmd = _make_cmd(
            CommandType.LOITER, CS2,
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        self.mgr._clients[CS2].move_to.assert_not_awaited()
        self.mgr._clients[CS2].set_mode.assert_awaited_once_with("LOITER")

    @pytest.mark.asyncio
    async def test_loiter_default_altitude(self):
        """LOITER with alt_m=0 should default to 50m."""
        cmd = _make_cmd(
            CommandType.LOITER, CS2,
            lat=44.66, lon=-63.58, alt_m=0.0,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        self.mgr._clients[CS2].move_to.assert_awaited_once_with(44.66, -63.58, 50.0)

    @pytest.mark.asyncio
    async def test_loiter_call_order(self):
        """LOITER must call move_to BEFORE set_mode (order matters)."""
        client = self.mgr._clients[CS2]
        call_order = []
        client.move_to = AsyncMock(side_effect=lambda *a: call_order.append("move_to"))
        client.set_mode = AsyncMock(side_effect=lambda *a: call_order.append("set_mode"))

        cmd = _make_cmd(CommandType.LOITER, CS2, lat=44.66, lon=-63.58, alt_m=80.0)
        await self.mgr.execute_command(cmd)
        assert call_order == ["move_to", "set_mode"]


# ---------------------------------------------------------------------------
# Regression: existing commands still work
# ---------------------------------------------------------------------------

class TestExistingCommandsRegression(TestVehicleManagerSetup):

    @pytest.mark.asyncio
    async def test_move_still_works(self):
        cmd = _make_cmd(CommandType.MOVE, CS1)
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "move_to"

    @pytest.mark.asyncio
    async def test_rtb_still_works(self):
        cmd = _make_cmd(CommandType.RTB, CS1, location=False)
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "rtb"

    @pytest.mark.asyncio
    async def test_takeoff_still_works(self):
        cmd = _make_cmd(
            CommandType.TAKEOFF, CS1,
            parameters={"alt_m": 25.0},
            location=False,
        )
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "takeoff"

    @pytest.mark.asyncio
    async def test_land_still_works(self):
        cmd = _make_cmd(CommandType.LAND, CS1, location=False)
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "land"

    @pytest.mark.asyncio
    async def test_overwatch_still_works(self):
        cmd = _make_cmd(CommandType.OVERWATCH, CS1)
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "overwatch"

    @pytest.mark.asyncio
    async def test_status_still_works(self):
        cmd = _make_cmd(CommandType.STATUS, CS1, location=False)
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is True
        assert result["action"] == "status"

    @pytest.mark.asyncio
    async def test_unknown_callsign(self):
        cmd = _make_cmd(CommandType.MOVE, "BOGUS-99")
        result = await self.mgr.execute_command(cmd)
        assert result["success"] is False
        assert "Unknown vehicle" in result["error"]
