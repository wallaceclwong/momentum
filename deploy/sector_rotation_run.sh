#!/usr/bin/env bash
# =============================================================================
# sector_rotation_run.sh — wrapper executed by systemd timer
#
# Purpose: run the monthly sector-rotation rebalance, but only if TODAY is
# the last Friday of the month.  Systemd timer fires every Friday 15:50 ET
# (=03:50 Sat HK) — this script is the gate.
#
# Environment required (systemd sets these via EnvironmentFile):
#   MOMENTUM_DIR     — repo path (e.g. /root/momentum)
#   MOMENTUM_VENV    — venv path  (e.g. /root/momentum/.venv)
#   SECTOR_NAV       — current portfolio NAV in USD
#   SECTOR_MODE      — "simulate" | "ibkr"  (default: simulate)
# =============================================================================
set -euo pipefail

MOMENTUM_DIR="${MOMENTUM_DIR:-/root/momentum}"
MOMENTUM_VENV="${MOMENTUM_VENV:-${MOMENTUM_DIR}/.venv}"
SECTOR_NAV="${SECTOR_NAV:-100000}"
SECTOR_MODE="${SECTOR_MODE:-simulate}"   # simulate | ibkr

# ── Gate: only run on last Friday of the month (evaluated in UTC) ─────
# The systemd timer fires at Fri 19:50 UTC. We must evaluate "what day is
# it" in UTC too — otherwise on the VM's local timezone (e.g. HKT) the date
# may already have rolled over to Saturday when the timer fires.
TODAY=$(TZ=UTC date +%u)                       # 1..7, Mon..Sun
if [ "$TODAY" != "5" ]; then
    echo "[$(TZ=UTC date -Iseconds) UTC] Not Friday (weekday=$TODAY) — skipping"
    exit 0
fi

# Last Friday check: UTC Friday + 7 days falls in the next UTC month
NEXT_WEEK_MONTH=$(TZ=UTC date -d "+7 days" +%m)
THIS_MONTH=$(TZ=UTC date +%m)
if [ "$NEXT_WEEK_MONTH" == "$THIS_MONTH" ]; then
    echo "[$(TZ=UTC date -Iseconds) UTC] Friday but not last of month — skipping"
    exit 0
fi

echo "[$(TZ=UTC date -Iseconds) UTC] LAST FRIDAY — running rebalance (mode=$SECTOR_MODE, nav=\$$SECTOR_NAV)"

# ── Translate mode → CLI flag ──────────────────────────────────
case "$SECTOR_MODE" in
    simulate) MODE_FLAG="--paper" ;;
    ibkr)     MODE_FLAG="--live"  ;;  # uses IBKR gateway; port in .env decides paper/live account
    dry_run)  MODE_FLAG="--dry-run" ;;
    *)
        echo "Unknown SECTOR_MODE: $SECTOR_MODE" >&2
        exit 1
        ;;
esac

# ── Execute ─────────────────────────────────────────────────────
cd "$MOMENTUM_DIR"
"$MOMENTUM_VENV/bin/python" sector_rotation_scheduler.py rebalance \
    "$MODE_FLAG" \
    --nav "$SECTOR_NAV"

echo "[$(date -Iseconds)] rebalance complete (mode=$SECTOR_MODE)"
