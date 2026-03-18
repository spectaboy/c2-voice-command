"""Learning system: command log, correction history, dynamic prompt builder."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent / "data"


class NLUContext:
    """Maintains command history and correction pairs for in-context learning."""

    def __init__(self, max_history: int = 20, data_dir: Optional[Path] = None):
        self.max_history = max_history
        self.data_dir = data_dir or DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.command_log_path = self.data_dir / "command_log.json"
        self.corrections_path = self.data_dir / "corrections.json"

        self.recent_commands: list[dict] = []
        self.corrections: list[dict] = []

        self._load()

    def _load(self):
        if self.corrections_path.exists():
            with open(self.corrections_path) as f:
                self.corrections = json.load(f)

        if self.command_log_path.exists():
            with open(self.command_log_path) as f:
                all_commands = json.load(f)
                self.recent_commands = all_commands[-self.max_history :]

    def log_command(self, transcript: str, command_dict: dict):
        entry = {
            "transcript": transcript,
            "command": command_dict,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.recent_commands.append(entry)
        if len(self.recent_commands) > self.max_history:
            self.recent_commands = self.recent_commands[-self.max_history :]

        # Append to full log on disk
        all_commands = []
        if self.command_log_path.exists():
            with open(self.command_log_path) as f:
                all_commands = json.load(f)
        all_commands.append(entry)
        with open(self.command_log_path, "w") as f:
            json.dump(all_commands, f, indent=2)

    def add_correction(self, wrong_transcript: str, wrong_parse: dict, correct_command: dict):
        correction = {
            "wrong_transcript": wrong_transcript,
            "wrong_parse": wrong_parse,
            "correct_command": correct_command,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.corrections.append(correction)
        with open(self.corrections_path, "w") as f:
            json.dump(self.corrections, f, indent=2)

    def build_context_block(self) -> str:
        """Build context string to inject into Claude's system prompt."""
        parts = []

        if self.corrections:
            parts.append("## Previous Corrections (learn from these)")
            for c in self.corrections[-10:]:  # Last 10 corrections
                parts.append(
                    f"- Transcript: \"{c['wrong_transcript']}\"\n"
                    f"  Wrong parse: {json.dumps(c['wrong_parse'])}\n"
                    f"  Correct: {json.dumps(c['correct_command'])}"
                )

        if self.recent_commands:
            parts.append("\n## Recent Successful Commands (for context)")
            for entry in self.recent_commands[-10:]:  # Last 10 for prompt size
                parts.append(
                    f"- \"{entry['transcript']}\" → {entry['command'].get('command_type', '?')} "
                    f"{entry['command'].get('vehicle_callsign', '?')}"
                )

        return "\n".join(parts)
