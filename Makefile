.PHONY: install gazebo sitl sitl-rover fly rover telemetry score clean

# ── Setup ────────────────────────────────────────────────────

install:
	chmod +x install.sh launch_gz.sh launch_sitl.sh
	./install.sh

# ── Launch (each in its own terminal) ────────────────────────

gazebo:
	./launch_gz.sh

sitl:
	./launch_sitl.sh copter

sitl-rover:
	./launch_sitl.sh rover

# ── Challenge ────────────────────────────────────────────────

score:
	@test -n "$(TEAM)" || (echo "Usage: make score TEAM=YourTeam" && exit 1)
	. venv/bin/activate && python challenge/scorer.py --team "$(TEAM)"

# ── Run demos (third terminal) ───────────────────────────────

fly:
	. venv/bin/activate && python mavsdk-app/src/demo_flight.py

rover:
	. venv/bin/activate && python mavsdk-app/src/demo_rover.py

telemetry:
	. venv/bin/activate && python mavsdk-app/src/telemetry_monitor.py

# ── Cleanup ──────────────────────────────────────────────────

clean:
	rm -rf ardupilot ardupilot_gazebo venv
	@echo "Cleaned. Run 'make install' to set up again."
