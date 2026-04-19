#!/usr/bin/env bash
# =============================================================================
# install_sector_rotation.sh — set up systemd service + timer on the VM
#
# Prerequisites:
#   1. Repo cloned to /root/momentum
#   2. Python venv created at /root/momentum/.venv and dependencies installed
#   3. ibkr_setup_vm.sh already run (IB Gateway installed as systemd service)
#   4. /root/momentum/.env configured with IBKR credentials
#   5. /root/momentum/.env.sector created from deploy/env.sector.example
#
# Run as root on the VM:
#   sudo bash /root/momentum/deploy/install_sector_rotation.sh
# =============================================================================
set -euo pipefail

MOMENTUM_DIR="/root/momentum"
DEPLOY_DIR="$MOMENTUM_DIR/deploy"
SYSTEMD_DIR="/etc/systemd/system"

echo "────────────────────────────────────────────────────────────"
echo " Sector Rotation — systemd installation"
echo "────────────────────────────────────────────────────────────"

# ── 1. Sanity checks ────────────────────────────────────────────
for path in \
    "$MOMENTUM_DIR/sector_rotation_scheduler.py" \
    "$MOMENTUM_DIR/.venv/bin/python" \
    "$DEPLOY_DIR/sector-rotation.service" \
    "$DEPLOY_DIR/sector-rotation.timer" \
    "$DEPLOY_DIR/sector_rotation_run.sh"
do
    if [ ! -e "$path" ]; then
        echo "ERROR: missing $path" >&2
        exit 1
    fi
done
if [ ! -f "$MOMENTUM_DIR/.env.sector" ]; then
    echo "ERROR: /root/momentum/.env.sector missing. Copy from deploy/env.sector.example." >&2
    exit 1
fi

chmod +x "$DEPLOY_DIR/sector_rotation_run.sh"

# ── 2. Install unit files ───────────────────────────────────────
echo "[1/4] Installing unit files..."
cp "$DEPLOY_DIR/sector-rotation.service" "$SYSTEMD_DIR/"
cp "$DEPLOY_DIR/sector-rotation.timer"   "$SYSTEMD_DIR/"
chmod 644 "$SYSTEMD_DIR/sector-rotation.service" "$SYSTEMD_DIR/sector-rotation.timer"

# ── 3. Reload + enable ──────────────────────────────────────────
echo "[2/4] Reloading systemd..."
systemctl daemon-reload

echo "[3/4] Enabling timer..."
systemctl enable  sector-rotation.timer
systemctl start   sector-rotation.timer

# ── 4. Status ───────────────────────────────────────────────────
echo "[4/4] Verifying..."
systemctl status sector-rotation.timer --no-pager || true
echo
systemctl list-timers sector-rotation.timer --no-pager || true

echo
echo "────────────────────────────────────────────────────────────"
echo "✓ Installed.  Next actions:"
echo "  • Verify timer fires on correct date:  systemctl list-timers sector-rotation.timer"
echo "  • Read logs after a run:               journalctl -u sector-rotation.service -n 200"
echo "  • Trigger NOW for testing:             systemctl start sector-rotation.service"
echo "  • Disable temporarily:                 systemctl disable --now sector-rotation.timer"
echo "────────────────────────────────────────────────────────────"
