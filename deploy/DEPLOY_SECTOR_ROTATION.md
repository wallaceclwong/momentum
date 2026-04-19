# Sector Rotation — Vultr VM Deployment Runbook

End-to-end steps to get the Antonacci UCITS sector rotation strategy running
on a Vultr (or any Debian/Ubuntu) VM, connected to your IBKR HK **paper**
account, firing automatically on the last Friday of each month.

---

## Phase 0 — Prerequisites (likely already done)

You probably already have these from the 33-stock scheduler setup:

- [ ] Vultr VM with Ubuntu 22.04 LTS (or similar Debian-family distro)
- [ ] SSH access as root (or sudo-able user)
- [ ] Momentum repo cloned to `/root/momentum`
- [ ] Python venv at `/root/momentum/.venv` with requirements installed
- [ ] IB Gateway installed via `ibkr_setup_vm.sh` and running as systemd service

If any of the above is missing, run the relevant prerequisite first.

---

## Phase 1 — Pull latest code

```bash
cd /root/momentum
git pull origin master            # get the sector-rotation commits
/root/momentum/.venv/bin/pip install -U python-dotenv ib_insync apscheduler
```

Verify new files exist:

```bash
ls -la sector_rotation_scheduler.py \
       backend/engine/sector_rotation.py \
       backend/engine/sector_executor.py \
       backend/ibkr/ucits_contracts.py \
       deploy/
```

---

## Phase 2 — Run unit tests on the VM

```bash
/root/momentum/.venv/bin/python -m pytest \
    tests/test_sector_rotation.py \
    tests/test_sector_executor.py -q
```

Expected: `16 passed`.

---

## Phase 3 — Verify signal generation (no IBKR required)

```bash
cd /root/momentum
/root/momentum/.venv/bin/python sector_rotation_scheduler.py screener
```

Expected output shows today's signal (SPY 12m return, top-3 sectors,
UCITS tickers).  Should match what you saw on your laptop.

---

## Phase 4 — Configure environment files

### 4a. Main IBKR connection env (`/root/momentum/.env`)

Make sure these are set (IB Gateway paper account):

```
IBKR_HOST=127.0.0.1
IBKR_PORT=4001            # 4001 = paper gateway
IBKR_CLIENT_ID=2          # DIFFERENT from 33-stock scheduler's clientId to avoid collision
IBKR_ACCOUNT_ID=DU1234567 # your paper account id
IBKR_LIVE=true            # allows IBKR connection; port decides paper vs live
```

> **Terminology note:** `IBKR_LIVE=true` means "connect to IBKR" — the account
> type (paper vs live-real-money) is determined by `IBKR_PORT` (4001=paper,
> 4002=live).  For paper-account testing, set `IBKR_LIVE=true` + `IBKR_PORT=4001`.

### 4b. Sector-rotation env (`/root/momentum/.env.sector`)

```bash
cp /root/momentum/deploy/env.sector.example /root/momentum/.env.sector
nano /root/momentum/.env.sector
```

Set:

```
MOMENTUM_DIR=/root/momentum
MOMENTUM_VENV=/root/momentum/.venv
SECTOR_NAV=330000                  # your bucket 2 size in USD
SECTOR_MODE=simulate                # start with simulate (no IBKR)
```

---

## Phase 5 — Dry-run on the VM (no IBKR needed)

```bash
cd /root/momentum
/root/momentum/.venv/bin/python sector_rotation_scheduler.py \
    rebalance --paper --nav 330000
```

Expected:
- Signal shown
- 3 BUY trades listed (IUIS, IUIT, IUMS at ~$110K each)
- `[REBAL] paper: simulated 3 fills`
- Entries written to `data/momentum_screener.db` tables `sector_signals` and `sector_rebalances`

Re-run the same command — it should produce **0 trades** (idempotent).

---

## Phase 6 — Install systemd service + timer

```bash
sudo bash /root/momentum/deploy/install_sector_rotation.sh
```

This installs and enables the timer.  Verify:

```bash
systemctl list-timers sector-rotation.timer
```

The "NEXT" column should show the upcoming Friday around 19:50 UTC.

---

## Phase 7 — Manual test fire (simulate last-Friday run)

```bash
sudo systemctl start sector-rotation.service
sudo journalctl -u sector-rotation.service -n 80 --no-pager
```

Expected log:

```
[YYYY-MM-DDThh:mm:ss+00:00] Not last Friday of month — skipping
```

(if today isn't last Friday)

To force-test the full rebalance path, temporarily remove the last-Friday
gate — edit `/root/momentum/deploy/sector_rotation_run.sh` and comment out
the `if [ "$NEXT_WEEK_MONTH" == "$THIS_MONTH" ]; then` block, then:

```bash
sudo systemctl start sector-rotation.service
sudo journalctl -u sector-rotation.service -n 200 --no-pager
```

**Remember to restore the gate after testing.**

---

## Phase 8 — Switch to IBKR paper mode

Once you're happy with simulate mode:

1. Confirm IB Gateway is running:
   ```bash
   systemctl status ib-gateway
   ```

2. Change `SECTOR_MODE` in `/root/momentum/.env.sector`:
   ```
   SECTOR_MODE=ibkr
   ```

3. Force-trigger a rebalance (after confirming paper account is empty):
   ```bash
   # Drop the last-Friday gate temporarily OR wait for May 29
   sudo systemctl start sector-rotation.service
   ```

4. Check IBKR TWS / paper account that orders appeared.

---

## Phase 9 — Last-Friday validation (May 29, 2026)

Nothing to do — the timer fires automatically at 19:50 UTC on May 29.

After it runs:

```bash
sudo journalctl -u sector-rotation.service --since "2026-05-29" --no-pager
/root/momentum/.venv/bin/python _check_sector_db.py  # if you saved this helper
```

Verify:
- Orders placed in IBKR paper account
- `sector_rebalances` table has new row with `mode='ibkr'`, `status='executed'`
- Log file `/var/log/sector-rotation.log` has end-to-end trace

---

## Phase 10 — Going live (real money)

**Only after 2–3 successful paper-mode cycles.**

1. Edit `/root/momentum/.env`:
   ```
   IBKR_PORT=4002          # switch to live gateway
   IBKR_ACCOUNT_ID=U1234567 # your live account
   ```

2. Restart IB Gateway (it needs to pick up the live credentials):
   ```bash
   systemctl restart ib-gateway
   ```

3. Paper-mode keeps working unchanged since your `.env.sector` still says
   `SECTOR_MODE=ibkr` — same flag, different account behind the port.

4. **Do a manual test with 1 share first** before letting the scheduler
   handle full capital.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| `No module named 'dotenv'` | Run `pip install python-dotenv` in venv |
| `IBKR_LIVE is not set to 'true'` | Fix `/root/momentum/.env` |
| Timer shows no "NEXT" time | `systemctl daemon-reload; systemctl restart sector-rotation.timer` |
| Orders not appearing in IBKR | Check `systemctl status ib-gateway` and `IBKR_PORT` matches account type |
| "clientId already in use" | Change `IBKR_CLIENT_ID` (must differ from 33-stock scheduler) |
| Timer fires but script exits "not last Friday" | Expected — it only runs on last Friday |

---

## Quick command reference

```bash
# Manual one-shot rebalance (any day)
cd /root/momentum && .venv/bin/python sector_rotation_scheduler.py \
    rebalance --paper --nav 330000

# See today's signal only
.venv/bin/python sector_rotation_scheduler.py screener

# Preview trades without executing
.venv/bin/python sector_rotation_scheduler.py plan --nav 330000

# Force timer to fire now (for testing)
sudo systemctl start sector-rotation.service

# Next scheduled run
systemctl list-timers sector-rotation.timer

# Logs
journalctl -u sector-rotation.service -n 200
tail -f /var/log/sector-rotation.log

# Disable temporarily
sudo systemctl disable --now sector-rotation.timer
```
