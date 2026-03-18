"""Start all C2 services. Run from project root: python scripts/start_all.py"""

import subprocess
import sys
import os
import time
import signal
import urllib.request
import urllib.error

# Ensure we're in the project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
sys.path.insert(0, PROJECT_ROOT)

SERVICES = [
    {"name": "WebSocket Hub", "module": "src.websocket_hub.server:app", "port": 8005, "wait": 10},
    {"name": "Coordinator",   "module": "src.coordinator.server:app",   "port": 8000, "wait": 10},
    {"name": "NLU Parser",    "module": "src.nlu.server:app",           "port": 8002, "wait": 10},
    {"name": "IFF Engine",    "module": "src.iff.server:app",           "port": 8004, "wait": 10},
    {"name": "Vehicle Bridge", "module": "src.vehicles.server:app",     "port": 8003, "wait": 30},
    {"name": "Voice ASR",     "module": "src.voice.server:app",         "port": 8001, "wait": 40},
]

processes = []


def check_health(port, timeout=2):
    """Check if a service is healthy."""
    try:
        url = f"http://127.0.0.1:{port}/health"
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.status == 200
    except Exception:
        return False


def kill_port(port):
    """Kill any process on the given port (Windows)."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines():
            if f"0.0.0.0:{port}" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                if pid and pid != "0":
                    subprocess.run(
                        ["taskkill", "/F", "/PID", pid],
                        capture_output=True, timeout=5
                    )
    except Exception:
        pass


def cleanup(signum=None, frame=None):
    """Stop all services."""
    print("\nStopping all services...")
    for proc in processes:
        try:
            proc.terminate()
        except Exception:
            pass
    time.sleep(1)
    for proc in processes:
        try:
            proc.kill()
        except Exception:
            pass
    # Belt and suspenders
    for svc in SERVICES:
        kill_port(svc["port"])
    print("All services stopped.")
    sys.exit(0)


def main():
    print("=== C2 Voice Command System ===")
    print(f"Python: {sys.version}")
    print(f"Working dir: {os.getcwd()}")
    print()

    # Clear old processes on our ports
    print("Clearing ports...")
    for svc in SERVICES:
        kill_port(svc["port"])
    time.sleep(2)

    print("Starting services...\n")

    for svc in SERVICES:
        name = svc["name"]
        module = svc["module"]
        port = svc["port"]
        max_wait = svc["wait"]

        cmd = [
            sys.executable, "-m", "uvicorn", module,
            "--host", "0.0.0.0",
            "--port", str(port),
            "--log-level", "warning",
        ]

        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            # Let service output go to console so you can see errors
        )
        processes.append(proc)

        # Wait for health
        started = False
        for i in range(max_wait):
            # Check if process crashed
            if proc.poll() is not None:
                print(f"  CRASH  {name} (:{port}) — process exited with code {proc.returncode}")
                break
            if check_health(port):
                print(f"  OK     {name} (:{port})")
                started = True
                break
            time.sleep(1)

        if not started and proc.poll() is None:
            print(f"  SLOW   {name} (:{port}) — still starting (will keep trying)")

    # Final status
    print("\n=== Final Status ===")
    passed = 0
    for svc in SERVICES:
        name = svc["name"]
        port = svc["port"]
        ok = check_health(port)
        status = "UP" if ok else "DOWN"
        if ok:
            passed += 1
        print(f"  {status:4s}  {name} (:{port})")

    print(f"\n{passed}/{len(SERVICES)} services running.")

    if passed == 0:
        print("\nNo services came up. Check for errors above.")
        print("Common issues:")
        print("  - Missing packages: pip install -r requirements.txt")
        print("  - Port in use: taskkill /F /IM python.exe, then retry")
        print("  - Import error: run 'python -m uvicorn src.websocket_hub.server:app --port 8005' manually to see the error")
        cleanup()
        return

    print("\nDashboard: cd src/dashboard && npm run dev")
    print("Press Ctrl+C to stop all services.\n")

    # Handle Ctrl+C
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Wait for all processes
    try:
        while True:
            # Check if any process died
            for i, proc in enumerate(processes):
                if proc.poll() is not None:
                    name = SERVICES[i]["name"]
                    # Don't spam - just note it once
            time.sleep(5)
    except KeyboardInterrupt:
        cleanup()


if __name__ == "__main__":
    main()
