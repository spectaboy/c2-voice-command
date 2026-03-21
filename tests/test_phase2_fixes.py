"""Tests for Phase 2 fixes: telemetry in NLU, sequential execution, honest status."""

from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from src.shared.schemas import (
    MilitaryCommand, CommandType, Domain, Location,
)


# ---------------------------------------------------------------------------
# Fix 4: Telemetry in NLU system prompt
# ---------------------------------------------------------------------------

class TestTelemetryInPrompt:

    def test_build_telemetry_info_formats_correctly(self):
        """_build_telemetry_info should format vehicle telemetry into readable lines."""
        from src.nlu.parser import _build_telemetry_info

        mock_vehicles = [
            {
                "callsign": "Alpha",
                "lat": 44.650000,
                "lon": -63.570000,
                "alt_m": 100.0,
                "mode": "GUIDED",
                "armed": True,
                "speed_mps": 15.0,
                "battery_pct": 85.0,
            }
        ]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_vehicles

        mock_client = MagicMock()
        mock_client.get.return_value = mock_resp
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)

        with patch("httpx.Client", return_value=mock_client):
            result = _build_telemetry_info()

        assert "Alpha" in result
        assert "GUIDED" in result
        assert "armed=True" in result
        assert "battery=85%" in result

    def test_build_telemetry_info_handles_failure(self):
        """_build_telemetry_info should return fallback when bridge is down."""
        from src.nlu.parser import _build_telemetry_info

        with patch("httpx.Client", side_effect=Exception("connection refused")):
            result = _build_telemetry_info()

        assert "unavailable" in result

    def test_system_prompt_has_telemetry_placeholder(self):
        """SYSTEM_PROMPT must contain {telemetry_info} placeholder."""
        from src.nlu.parser import SYSTEM_PROMPT
        assert "{telemetry_info}" in SYSTEM_PROMPT

    def test_system_prompt_has_telemetry_section_header(self):
        """SYSTEM_PROMPT must have a telemetry section header."""
        from src.nlu.parser import SYSTEM_PROMPT
        assert "Live Vehicle Telemetry" in SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Fix 5: Sequential command execution
# ---------------------------------------------------------------------------

class TestSequentialExecution:

    def test_emit_transcript_has_delay_logic(self):
        """The _emit_transcript function should have a delay between commands."""
        import inspect
        from src.voice.server import _emit_transcript

        source = inspect.getsource(_emit_transcript)
        # Verify the delay logic exists
        assert "asyncio.sleep" in source
        # Verify it's inside a compound-command check
        assert "len(commands) - 1" in source

    def test_emit_transcript_has_indexed_loop(self):
        """The command loop should use enumerate for indexing."""
        import inspect
        from src.voice.server import _emit_transcript

        source = inspect.getsource(_emit_transcript)
        assert "enumerate(commands)" in source


# ---------------------------------------------------------------------------
# Fix 6: Honest execution status
# ---------------------------------------------------------------------------

class TestHonestStatus:

    def test_broadcast_uses_command_sent(self):
        """Execution broadcast should use 'Command sent.' not just 'Executed.'"""
        import inspect
        from src.voice.server import _emit_transcript

        source = inspect.getsource(_emit_transcript)
        assert "Command sent." in source


# ---------------------------------------------------------------------------
# Parser conversion still works after telemetry addition
# ---------------------------------------------------------------------------

class TestParserStillWorks:

    @patch("src.nlu.parser._resolve_callsign", return_value=("Alpha", Domain.AIR))
    def test_move_vehicle_still_converts(self, mock_resolve):
        """move_vehicle tool call should still produce correct MilitaryCommand."""
        from src.nlu.parser import _tool_result_to_command

        tool_input = {"callsign": "Alpha", "lat": 44.66, "lon": -63.58, "alt_m": 100.0}
        cmd = _tool_result_to_command("move_vehicle", tool_input, "move alpha to bridge")
        assert cmd.command_type == CommandType.MOVE
        assert cmd.location is not None
        assert cmd.location.lat == 44.66

    @patch("src.nlu.parser._resolve_callsign", return_value=("Alpha", Domain.AIR))
    def test_loiter_at_still_converts(self, mock_resolve):
        """loiter_at tool call should produce MilitaryCommand with location."""
        from src.nlu.parser import _tool_result_to_command

        tool_input = {"callsign": "Alpha", "lat": 44.66, "lon": -63.58, "alt_m": 80.0, "duration_min": 5}
        cmd = _tool_result_to_command("loiter_at", tool_input, "loiter at bridge")
        assert cmd.command_type == CommandType.LOITER
        assert cmd.location is not None
        assert cmd.location.lat == 44.66
        assert cmd.parameters.get("duration_min") == 5

    @patch("src.nlu.parser._resolve_callsign", return_value=("Alpha", Domain.AIR))
    def test_engage_target_still_converts(self, mock_resolve):
        """engage_target tool call should produce MilitaryCommand."""
        from src.nlu.parser import _tool_result_to_command

        tool_input = {"callsign": "Alpha", "target_uid": "HOSTILE-01"}
        cmd = _tool_result_to_command("engage_target", tool_input, "engage hostile one")
        assert cmd.command_type == CommandType.ENGAGE
        assert cmd.parameters.get("target_uid") == "HOSTILE-01"
        assert cmd.requires_confirmation is True
