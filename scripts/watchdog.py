#!/usr/bin/env python3
"""
DeviceAtlas — Scraper Watchdog (cron-friendly)

Designed to run every 5 minutes via cron. Each invocation:
  1. Checks each worker by scanning `ps aux` for its command pattern
  2. If not running AND not done → starts it (appending to its log)
  3. If stale (log not updated in STALE_MINUTES) → kills + restarts
  4. Refreshes /tmp/mgmt_token.txt from env before starting workers

No persistent state — process detection is done via ps each run,
so this survives session restarts, reboots, and watchdog restarts.

Cron setup (runs every 5 min):
  */5 * * * * /usr/bin/python3 -u /workspace/deviceatlas/scripts/watchdog.py >> /tmp/watchdog.log 2>&1

Usage (manual):
  python3 -u scripts/watchdog.py
"""

import os, subprocess, signal, time, sys
from datetime import datetime

SCRIPTS_DIR   = os.path.dirname(os.path.abspath(__file__))
STALE_MINUTES = 10    # Kill + restart if no log output for this many minutes
ENV           = os.environ.copy()


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{ts()}] {msg}", flush=True)


# ── Worker definitions ─────────────────────────────────────────────────────────
# ps_pattern: unique substring to find this process in `ps aux` output
WORKERS = [
    {
        "name":        "enrich-structured-0",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-structured.py", "0"],
        "log":         "/tmp/enrich-s0.log",
        "ps_pattern":  "enrich-structured.py 0",
        "done_marker": "No more un-enriched devices — done!",
    },
    {
        "name":        "enrich-structured-1",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-structured.py", "1"],
        "log":         "/tmp/enrich-s1.log",
        "ps_pattern":  "enrich-structured.py 1",
        "done_marker": "No more un-enriched devices — done!",
    },
    {
        "name":        "eudamed-import",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/import-eudamed.py"],
        "log":         "/tmp/eudamed-import.log",
        "ps_pattern":  "import-eudamed.py",
        "done_marker": "IMPORT COMPLETE",
    },
    {
        "name":        "hc-enrich-0",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-hc-devices.py", "0"],
        "log":         "/tmp/hc-enrich-w0.log",
        "ps_pattern":  "enrich-hc-devices.py 0",
        "done_marker": "No more devices. Total enriched:",
    },
    {
        "name":        "hc-enrich-1",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-hc-devices.py", "1"],
        "log":         "/tmp/hc-enrich-w1.log",
        "ps_pattern":  "enrich-hc-devices.py 1",
        "done_marker": "No more devices. Total enriched:",
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────
def is_running(pattern: str) -> tuple[bool, int | None]:
    """Check if a process matching pattern is running. Returns (running, pid)."""
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if pattern in line and "grep" not in line and "watchdog" not in line:
                parts = line.split()
                try:
                    return True, int(parts[1])
                except (IndexError, ValueError):
                    return True, None
        return False, None
    except Exception:
        return False, None


def is_done(worker: dict) -> bool:
    """Check if the log contains the completion marker."""
    marker   = worker.get("done_marker", "")
    log_path = worker["log"]
    if not marker or not os.path.exists(log_path):
        return False
    try:
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 8192))
            tail = f.read().decode("utf-8", errors="replace")
        return marker in tail
    except Exception:
        return False


def log_age_seconds(log_path: str) -> float | None:
    try:
        return time.time() - os.path.getmtime(log_path)
    except Exception:
        return None


def kill_by_pattern(pattern: str):
    """Kill all processes matching pattern."""
    try:
        result = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            if pattern in line and "grep" not in line and "watchdog" not in line:
                parts = line.split()
                try:
                    pid = int(parts[1])
                    os.kill(pid, signal.SIGKILL)
                    log(f"  Killed pid={pid} ({pattern})")
                except Exception:
                    pass
    except Exception:
        pass


def start_worker(worker: dict):
    """Start worker process, appending to its log file."""
    name     = worker["name"]
    log_path = worker["log"]

    # Write a restart banner into the log
    with open(log_path, "a") as lf:
        lf.write(f"\n{'='*60}\n[watchdog] Starting {name} at {ts()}\n{'='*60}\n")

    log_file = open(log_path, "a")
    proc = subprocess.Popen(
        worker["cmd"],
        stdout=log_file,
        stderr=log_file,
        env=ENV,
        start_new_session=True,   # Detach from our process group
        close_fds=True,
    )
    log(f"  ✓ Started {name} (pid={proc.pid})")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    log(f"{'='*60}")
    log(f"DeviceAtlas Watchdog — checking {len(WORKERS)} workers")
    log(f"{'='*60}")

    # Refresh mgmt token file so scraper scripts always have a valid token
    token = ENV.get("SUPABASE_MGMT_TOKEN", "")
    if token:
        with open("/tmp/mgmt_token.txt", "w") as f:
            f.write(token)
        log("Refreshed /tmp/mgmt_token.txt")

    actions = 0
    for worker in WORKERS:
        name      = worker["name"]
        pattern   = worker["ps_pattern"]
        log_path  = worker["log"]

        # 1. Already completed?
        if is_done(worker):
            log(f"DONE  {name} — skipping")
            continue

        running, pid = is_running(pattern)
        age          = log_age_seconds(log_path)

        # 2. Stale — process is running but log is frozen
        if running and age is not None and age > STALE_MINUTES * 60:
            age_m = age / 60
            log(f"STALE {name} (pid={pid}, {age_m:.1f}m since last output) — killing & restarting")
            kill_by_pattern(pattern)
            time.sleep(3)
            start_worker(worker)
            actions += 1

        # 3. Dead — not running at all
        elif not running:
            log(f"DEAD  {name} — starting")
            start_worker(worker)
            actions += 1
            time.sleep(2)   # Stagger starts

        # 4. Healthy
        else:
            age_s = f"{age:.0f}s ago" if age is not None else "unknown"
            log(f"OK    {name} (pid={pid}, last output {age_s})")

    log(f"Done — {actions} action(s) taken")


if __name__ == "__main__":
    main()
