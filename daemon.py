"""
Blogging Agent daemon — runs continuously, acts when needed.

Each poll cycle (default 60 min) the daemon works through a priority list:
  1. Research      — keep topic queue topped up (MIN_QUEUE_SIZE)
  2. Write         — publish one article per day
  3. Monitor       — snapshot GSC + GA4 performance (every 7 days)
  4. Correct       — fix posts flagged by the monitor (runs after any monitor pass)
  5. Refresh       — rewrite stale articles with new data (every 14 days)

Start:  python daemon.py
Stop:   Ctrl+C

Logs to stdout and logs/daemon.log
"""

import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import config
from storage.db import init_db, get_all_topics

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/daemon.log"),
    ],
)
log = logging.getLogger("daemon")

_stop = False

MONITOR_INTERVAL_DAYS  = 7
REFRESH_INTERVAL_DAYS  = 14


def _handle_signal(sig, frame):
    global _stop
    log.info("Shutdown signal received — stopping after current task.")
    _stop = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def _queued_count() -> int:
    return len(get_all_topics(status="queued"))


def _days_since_monitor() -> float:
    """Days since the last performance snapshot was taken."""
    from storage.db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(snapshot_date) as last FROM performance_snapshots"
        ).fetchone()
    if not row or not row["last"]:
        return float("inf")
    try:
        last = datetime.fromisoformat(row["last"])
        return (datetime.now() - last).total_seconds() / 86400
    except Exception:
        return float("inf")


def _days_since_agent(agent_name: str) -> float:
    """Days since an agent last completed successfully (via agent_runs table)."""
    from storage.db import get_agent_runs
    runs = get_agent_runs(limit=1, agent_name=agent_name, status="success")
    if not runs:
        return float("inf")
    try:
        last = datetime.fromisoformat(runs[0]["finished_at"])
        return (datetime.now() - last).total_seconds() / 86400
    except Exception:
        return float("inf")


def main():
    init_db()

    log.info("Blogging Agent daemon started")
    log.info(f"Provider: {config.PROVIDER} / Model: {config.MODEL}")
    log.info(f"Poll interval: {config.POLL_INTERVAL_MINUTES}m | "
             f"Min queue: {config.MIN_QUEUE_SIZE} | "
             f"Max articles/day: {config.MAX_ARTICLES_PER_DAY}")
    log.info(f"Approval mode: {config.APPROVAL_MODE}")
    log.info(f"Monitor every {MONITOR_INTERVAL_DAYS}d | Refresh every {REFRESH_INTERVAL_DAYS}d")

    articles_today = 0
    last_date = ""

    while not _stop:
        today = datetime.now().strftime("%Y-%m-%d")

        # Reset daily counter at midnight
        if today != last_date:
            if last_date:
                log.info(f"New day — resetting article counter (wrote {articles_today} yesterday)")
            articles_today = 0
            last_date = today

        queued = _queued_count()
        log.info(f"Queue check: {queued} topic(s) queued | {articles_today}/{config.MAX_ARTICLES_PER_DAY} written today")

        # ── 1. Research if queue is running low ───────────────────────────────
        if queued < config.MIN_QUEUE_SIZE:
            log.info(f"Queue below {config.MIN_QUEUE_SIZE} — running Research Agent...")
            try:
                from orchestrator import run_research
                run_research()
                queued = _queued_count()
                log.info(f"Research done. Queue now: {queued} topic(s)")
            except Exception as e:
                log.error(f"Research failed: {e}", exc_info=True)

        # ── 2. Write next article if daily limit not reached ──────────────────
        if queued > 0 and articles_today < config.MAX_ARTICLES_PER_DAY:
            log.info("Writing next article...")
            try:
                from orchestrator import run_write
                run_write()
                articles_today += 1
                log.info(f"Write complete. Articles today: {articles_today}/{config.MAX_ARTICLES_PER_DAY}")
            except Exception as e:
                log.error(f"Write failed: {e}", exc_info=True)
        elif articles_today >= config.MAX_ARTICLES_PER_DAY:
            log.info(f"Daily limit reached ({config.MAX_ARTICLES_PER_DAY}). Resuming tomorrow.")
        elif queued == 0:
            log.info("Queue still empty after research. Will retry next cycle.")

        # ── 3. Monitor — snapshot GSC + GA4 performance every 7 days ─────────
        days_monitor = _days_since_monitor()
        if days_monitor >= MONITOR_INTERVAL_DAYS:
            log.info(f"Monitor due ({days_monitor:.1f}d since last run) — snapshotting performance...")
            try:
                from orchestrator import run_monitor
                run_monitor()
                log.info("Monitor complete.")
            except Exception as e:
                log.error(f"Monitor failed: {e}", exc_info=True)

        # ── 4. Correct — fix any posts flagged by the monitor ─────────────────
        try:
            from storage.db import get_flagged_posts
            flagged = get_flagged_posts()
            if flagged:
                log.info(f"{len(flagged)} flagged post(s) — running Corrector Agent...")
                from orchestrator import run_correction
                run_correction()
                log.info("Corrector complete.")
        except Exception as e:
            log.error(f"Corrector failed: {e}", exc_info=True)

        # ── 5. Refresh — rewrite stale articles every 14 days ─────────────────
        days_refresh = _days_since_agent("refresh")
        if days_refresh >= REFRESH_INTERVAL_DAYS:
            log.info(f"Refresh due ({days_refresh:.1f}d since last run) — checking for stale articles...")
            try:
                from orchestrator import run_refresh
                run_refresh()
                log.info("Refresh complete.")
            except Exception as e:
                log.error(f"Refresh failed: {e}", exc_info=True)

        # ── Sleep until next check ────────────────────────────────────────────
        if not _stop:
            log.info(f"Sleeping {config.POLL_INTERVAL_MINUTES} minutes...")
            for _ in range(config.POLL_INTERVAL_MINUTES * 60 // 5):
                if _stop:
                    break
                time.sleep(5)

    log.info("Daemon stopped.")


if __name__ == "__main__":
    main()
