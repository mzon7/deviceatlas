#!/usr/bin/env python3
"""
DeviceAtlas — Scraper Watchdog

Monitors all background scraper processes and auto-restarts them if:
  - The process has died (PID no longer exists)
  - The log file hasn't been updated in STALE_MINUTES (process hung)

Skips workers whose log contains the known "done" sentinel string.

Usage:
  nohup python3 -u scripts/watchdog.py > /tmp/watchdog.log 2>&1 &
  tail -f /tmp/watchdog.log
"""

import os, subprocess, time, signal
from datetime import datetime

SCRIPTS_DIR   = os.path.dirname(os.path.abspath(__file__))
STALE_MINUTES = 8     # Mark as stalled if no log output for this many minutes
CHECK_EVERY   = 60    # How often to check (seconds)
KILL_WAIT     = 5     # Seconds to wait after SIGKILL before restarting

ENV = os.environ.copy()

# ── Worker definitions ────────────────────────────────────────────────────────
WORKERS = [
    {
        "name":        "enrich-structured-0",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-structured.py", "0"],
        "log":         "/tmp/enrich-s0.log",
        "done_marker": "No more un-enriched devices — done!",
    },
    {
        "name":        "enrich-structured-1",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-structured.py", "1"],
        "log":         "/tmp/enrich-s1.log",
        "done_marker": "No more un-enriched devices — done!",
    },
    {
        "name":        "eudamed-import",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/import-eudamed.py"],
        "log":         "/tmp/eudamed-import.log",
        "done_marker": "IMPORT COMPLETE",
    },
    {
        "name":        "hc-enrich-0",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-hc-devices.py", "0"],
        "log":         "/tmp/hc-enrich-w0.log",
        "done_marker": "No more devices. Total enriched:",
    },
    {
        "name":        "hc-enrich-1",
        "cmd":         ["python3", "-u", f"{SCRIPTS_DIR}/enrich-hc-devices.py", "1"],
        "log":         "/tmp/hc-enrich-w1.log",
        "done_marker": "No more devices. Total enriched:",
    },
]

# ── State ─────────────────────────────────────────────────────────────────────
pids: dict[str, int] = {}          # name → pid
restart_counts: dict[str, int] = {}  # name → how many times restarted


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str):
    print(f"[{ts()}] {msg}", flush=True)


# ── Process helpers ────────────────────────────────────────────────────────────
def is_alive(name: str) -> bool:
    pid = pids.get(name)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def kill_worker(name: str):
    pid = pids.get(name)
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGKILL)
        log(f"  Sent SIGKILL to {name} (pid={pid})")
    except Exception as e:
        log(f"  Kill failed for {name}: {e}")
    time.sleep(KILL_WAIT)


def start_worker(worker: dict, append: bool = True):
    name     = worker["name"]
    log_path = worker["log"]
    mode     = "a" if append else "w"

    log(f"  → Starting {name} (log={'append' if append else 'new'}: {log_path})")
    with open(log_path, mode) as lf:
        lf.write(f"\n{'='*60}\n[watchdog] Restart at {ts()}\n{'='*60}\n")

    log_file = open(log_path, "a")
    proc = subprocess.Popen(
        worker["cmd"],
        stdout=log_file,
        stderr=log_file,
        env=ENV,
        start_new_session=True,
    )
    pids[name] = proc.pid
    restart_counts[name] = restart_counts.get(name, 0) + 1
    log(f"  ✓ {name} started (pid={proc.pid}, restarts={restart_counts[name]})")


# ── Done / stale checks ────────────────────────────────────────────────────────
def is_done(worker: dict) -> bool:
    marker   = worker.get("done_marker", "")
    log_path = worker["log"]
    if not marker or not os.path.exists(log_path):
        return False
    try:
        # Read last 4 KB — done marker should be near the end
        with open(log_path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode("utf-8", errors="replace")
        return marker in tail
    except Exception:
        return False


def log_age_seconds(log_path: str) -> float | None:
    """Returns seconds since log file was last modified, or None if missing."""
    try:
        return time.time() - os.path.getmtime(log_path)
    except Exception:
        return None


# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    log("=" * 60)
    log("DeviceAtlas Scraper Watchdog")
    log(f"  Workers:         {len(WORKERS)}")
    log(f"  Stale threshold: {STALE_MINUTES} minutes")
    log(f"  Check interval:  {CHECK_EVERY} seconds")
    log("=" * 60)

    # Refresh mgmt token file so worker scripts pick up the current token
    token = ENV.get("SUPABASE_MGMT_TOKEN", "")
    if token:
        with open("/tmp/mgmt_token.txt", "w") as f:
            f.write(token)
        log("Refreshed /tmp/mgmt_token.txt")

    # Initial start — stagger by 3s each so they don't hammer the DB simultaneously
    for i, worker in enumerate(WORKERS):
        name = worker["name"]
        if is_done(worker):
            log(f"SKIP {name}: already complete (done marker found in log)")
            continue
        if i > 0:
            time.sleep(3)
        start_worker(worker, append=True)

    log(f"\nWatchdog loop running — checking every {CHECK_EVERY}s ...\n")

    while True:
        time.sleep(CHECK_EVERY)

        for worker in WORKERS:
            name     = worker["name"]
            log_path = worker["log"]

            if is_done(worker):
                # If it somehow completed, retire the tracked PID
                if name in pids:
                    log(f"✓ {name}: done — retiring")
                    del pids[name]
                continue

            alive = is_alive(name)
            age   = log_age_seconds(log_path)

            if not alive:
                log(f"⚠ {name}: DEAD — restarting")
                start_worker(worker, append=True)

            elif age is not None and age > STALE_MINUTES * 60:
                age_min = age / 60
                log(f"⚠ {name}: STALE ({age_min:.1f}m since last output) — killing & restarting")
                kill_worker(name)
                start_worker(worker, append=True)

            # else: running and fresh — no action


if __name__ == "__main__":
    main()
