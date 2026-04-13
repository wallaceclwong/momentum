#!/usr/bin/env bash
# =============================================================================
# ibkr_setup_vm.sh — One-time IB Gateway headless setup for Ubuntu/Debian VM
#
# Run as root on the VM:
#   chmod +x ibkr_setup_vm.sh
#   ./ibkr_setup_vm.sh
#
# After running:
#   1. Fill /root/momentum/.env with IBKR credentials
#   2. systemctl start ib-gateway
#   3. Test: python ibkr_scheduler.py --now --dry-run
#   4. Go live: set IBKR_LIVE=true in .env, then python ibkr_scheduler.py --now
# =============================================================================
set -e

IB_VERSION="10.30.1l"
IB_INSTALL_DIR="/opt/ibgateway"
IB_DATA_DIR="/root/.ibgateway"
MOMENTUM_DIR="/root/momentum"

echo "======================================"
echo " IB Gateway Headless Setup"
echo "======================================"

# ── 1. System dependencies ─────────────────────────────────────
echo "[1/6] Installing system dependencies..."
apt-get update -q
apt-get install -y -q xvfb x11vnc unzip wget default-jdk curl

# ── 2. Download IB Gateway installer ──────────────────────────
echo "[2/6] Downloading IB Gateway ${IB_VERSION}..."
mkdir -p "$IB_INSTALL_DIR"
cd /tmp

IB_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"
wget -q -O ibgateway_install.sh "$IB_URL"
chmod +x ibgateway_install.sh

# ── 3. Install silently ────────────────────────────────────────
echo "[3/6] Installing IB Gateway..."
./ibgateway_install.sh -q -dir "$IB_INSTALL_DIR" 2>/dev/null || true

# ── 4. Configure IB Gateway for auto-login ────────────────────
echo "[4/6] Configuring IB Gateway..."
mkdir -p "$IB_DATA_DIR"

# jts.ini — IB Gateway settings
cat > "$IB_DATA_DIR/jts.ini" << 'EOF'
[IBGateway]
TradingMode=paper
PaperUsername=
PaperPassword=
LiveUsername=
LivePassword=
AutoRestart=yes
MinimizeToTray=no
AutoRestartTime=11:59 PM
ExistingSessionDetectedAction=manual
EOF

echo ""
echo "  *** ACTION REQUIRED ***"
echo "  Edit $IB_DATA_DIR/jts.ini and fill in your IBKR credentials."
echo "  Set TradingMode=live for live trading, paper for paper trading."
echo ""

# ── 5. Create systemd service for IB Gateway ──────────────────
echo "[5/6] Creating ib-gateway systemd service..."

cat > /etc/systemd/system/ib-gateway.service << EOF
[Unit]
Description=Interactive Brokers Gateway (headless)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$IB_INSTALL_DIR
Environment=DISPLAY=:1
ExecStartPre=/usr/bin/Xvfb :1 -screen 0 1024x768x24 &
ExecStart=$IB_INSTALL_DIR/ibgateway
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 6. Create swap-over script for momentum-scheduler ─────────
echo "[6/6] Creating momentum-scheduler-ibkr systemd service..."

cat > /etc/systemd/system/momentum-scheduler-ibkr.service << EOF
[Unit]
Description=Momentum IBKR Scheduler
After=network.target ib-gateway.service
Requires=ib-gateway.service

[Service]
Type=simple
User=root
WorkingDirectory=$MOMENTUM_DIR
ExecStart=$MOMENTUM_DIR/.venv/bin/python ibkr_scheduler.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ib-gateway.service
systemctl enable momentum-scheduler-ibkr.service

echo ""
echo "======================================"
echo " Setup complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "  1. Edit $IB_DATA_DIR/jts.ini with your IBKR username/password"
echo "  2. Edit $MOMENTUM_DIR/.env:"
echo "       IBKR_HOST=127.0.0.1"
echo "       IBKR_PORT=4001          # 4001=paper, 4002=live"
echo "       IBKR_CLIENT_ID=1"
echo "       IBKR_ACCOUNT_ID=UXXXXXXX"
echo "       IBKR_LIVE=false         # set true for live orders"
echo ""
echo "  3. Start IB Gateway:"
echo "       systemctl start ib-gateway"
echo ""
echo "  4. Test dry-run rebalance:"
echo "       cd $MOMENTUM_DIR && python ibkr_scheduler.py --now --dry-run"
echo ""
echo "  5. When ready to go live:"
echo "       # Set IBKR_LIVE=true in .env, then:"
echo "       systemctl stop momentum-scheduler        # stop E*Trade scheduler"
echo "       systemctl start momentum-scheduler-ibkr  # start IBKR scheduler"
echo ""
