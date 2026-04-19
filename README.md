# S&P 500 Momentum — Two-Strategy System

A quantitative momentum strategy platform for long-term investors, featuring
two parallel tracks backed by a unified backtesting engine, live screener,
and automated monthly rebalance scheduler.

| Strategy | Universe | Target | Estate Tax | Operational Load |
|---|---|---:|---|---|
| **33-stock S&P 500 Momentum** | ~500 US large-caps | 33 positions (3 per sector) | ⚠️ Exposed | High |
| **UCITS Sector Rotation** (Antonacci) | 11 sector ETFs | 3 positions + cash | ✅ None | Low |

Both strategies share the same backtest infrastructure, survivorship-bias-corrected
point-in-time S&P 500 constituents, and regime-aware risk management primitives.

---

## Investment Thesis

### Why two strategies?

The **33-stock strategy** was the original design — pick the top-3 momentum
stocks in each of 11 GICS sectors monthly. After correcting a survivorship
bias in the backtest (commit `21f53a3`), the honest pre-tax CAGR is ~9.5%
over 2015–2026 (TEST window), down from the ~17% survivorship-inflated
number originally observed.

The **UCITS Sector Rotation strategy** (commit `99d0313` onwards) was added
specifically to address a material concern: **Hong Kong non-resident aliens
face 30% effective US estate tax on US-situs assets above a $60K exemption**.
On a $330K direct-US-stocks bucket over a 15-year horizon, that's ~$350K
of expected estate tax — a haircut that turns a 9.1% after-WHT CAGR into
just a 6.7% effective CAGR.

Ireland-domiciled UCITS sector ETFs are **not US-situs**, eliminating estate
tax entirely, and the Ireland-US tax treaty halves dividend withholding
(15% vs 30%). Combined with the Antonacci 12-month absolute-momentum trend
filter, the UCITS strategy backtests at ~10.1% effective after-tax CAGR —
a **+3.4 pts/year advantage** and **+$530K terminal wealth gap** over
15 years on $330K.

### Antonacci filter (current default for sector rotation)

Rule (one decision per month):

1. **If SPY 12-month total return > 0** → buy top-3 sectors by 12-minus-1
   month momentum, equal weight (33.3% each)
2. **If SPY 12-month total return ≤ 0** → go to cash

Chosen after a 5-variant comparison (commit `18bab31`): outperforms both
plain top-K momentum and Faber 10/12-month SMA variants on both CAGR
(TEST 10.4%, TRAIN 8.7%) and drawdown (−25% in 2008 GFC vs −45% plain).
Cleanly handles slow bears (dotcom 2000–02, GFC 2007–09, 2022) without the
whipsaw cost of SMA-crossover filters in choppy bull markets.

---

## Performance (post-survivorship-bias-fix, honest numbers)

All windows tested on the same data cache; metrics are pre-tax unless noted.

| Period | 33-stock CAGR | Sector Rotation (Antonacci) CAGR |
|---|---:|---:|
| Full history 2000–2026 (26yr) | — | **9.53%** / Sharpe 0.43 |
| TRAIN 2000–2014 | 11.88% / DD −9.6% | 8.74% / DD −25.3% |
| TEST 2015–2026 (OOS) | 9.52% / DD −13.4% | **10.39%** / DD −30.2% |
| P5 2020–2024 (recent regime) | 6.32% / Sharpe 0.16 | **10.12%** / Sharpe 0.55 |

### After-tax 15-year terminal wealth ($330K starting, HK NRA investor)

| Strategy | Pre-tax CAGR | After-WHT | Terminal Net | Effective CAGR |
|---|---:|---:|---:|---:|
| 33-stock US direct | 9.52% | 9.10% | **$870,582** | 6.68% |
| UCITS Antonacci (estate-tax-free) | 10.39% | 10.12% | **$1,400,892** | **10.12%** |
| **Difference** | +0.87 pts | +1.02 pts | **+$530,310 (+61%)** | +3.44 pts/yr |

---

## Quick Start

### Run today's sector rotation signal

```bash
# From repo root, with venv activated
python sector_rotation_scheduler.py screener
```

Output: Antonacci trend verdict + 11-sector momentum ranking + UCITS tickers to buy.

### Backtest all variants

```bash
python run_sector_backtest.py                 # default: Antonacci + abs momentum
python run_sector_backtest.py --no-trend      # plain top-3 momentum
python run_sector_filter_comparison.py        # side-by-side 5-variant sweep
```

### Unit tests

```bash
python -m pytest tests/test_sector_rotation.py tests/test_sector_executor.py -v
```

17/17 passing as of commit `9699ba9`.

---

## Architecture

### Strategy + backtest core

| File | Purpose |
|---|---|
| `backend/config.py` | Single source of truth for all strategy parameters |
| `backend/data/sp500.py` | Point-in-time S&P 500 constituents (fixes survivorship bias) |
| `backend/engine/backtest.py` | 33-stock backtest engine |
| `backend/engine/sector_rotation.py` | UCITS sector rotation strategy + backtest |
| `backend/engine/sector_executor.py` | Signal → trades → DB persistence (pure logic) |
| `backend/engine/momentum.py` | 33-stock composite score calculation |
| `backend/engine/regime.py` | 5-state VIX+MA market regime filter (33-stock) |

### IBKR integration

| File | Purpose |
|---|---|
| `backend/ibkr/gateway.py` | IB Gateway connection singleton |
| `backend/ibkr/account.py` | Positions + cash queries |
| `backend/ibkr/trader.py` | 33-stock order placement (Adaptive algo) |
| `backend/ibkr/ucits_contracts.py` | UCITS ETF contract specs (LSE, USD class) |

### Schedulers + notifications

| File | Purpose |
|---|---|
| `ibkr_scheduler.py` | 33-stock monthly rebalance scheduler |
| `sector_rotation_scheduler.py` | Sector rotation CLI + scheduler |
| `backend/notify/telegram.py` | Telegram bot notifications |

### Deployment (VM via systemd)

| File | Purpose |
|---|---|
| `deploy/sector-rotation.service` | systemd oneshot unit |
| `deploy/sector-rotation.timer` | Fri 15:00 UTC = 23:00 HKT trigger |
| `deploy/sector_rotation_run.sh` | Wrapper with UTC-based last-Friday gate |
| `deploy/install_sector_rotation.sh` | One-shot installer |
| `deploy/DEPLOY_SECTOR_ROTATION.md` | 10-phase deployment runbook |

---

## Sector Rotation CLI

```bash
# Print today's signal only (no side effects)
python sector_rotation_scheduler.py screener

# Show rebalance plan (persists dry_run record to DB)
python sector_rotation_scheduler.py plan --nav 330000

# Test Telegram bot
python sector_rotation_scheduler.py notify-test

# Execute rebalance — three modes:
python sector_rotation_scheduler.py rebalance --dry-run --nav 330000   # plan only, no DB
python sector_rotation_scheduler.py rebalance --paper   --nav 330000   # simulated fills, DB only
python sector_rotation_scheduler.py rebalance --live    --nav 330000   # real IBKR orders

# Blocking scheduler loop (alternative to systemd timer)
python sector_rotation_scheduler.py schedule --paper --nav 330000
```

### Mode semantics

| Flag | DB writes | IBKR connection | Real orders |
|---|---|---|---|
| `--dry-run` | planned row | no | no |
| `--paper` | executed row with simulated fills | no | no |
| `--live` | executed row + IBKR fills | **yes** | **yes (paper or real based on `IBKR_PORT`)** |

**`IBKR_PORT=4001`** → IBKR paper account (fake money, real order routing)
**`IBKR_PORT=4002`** → IBKR live account (**real money**)

---

## Configuration

### `.env` (project root) — IBKR + Telegram credentials

```ini
# Telegram (optional — notifications silently no-op if empty)
TELEGRAM_BOT_TOKEN=<your_bot_token>
TELEGRAM_CHAT_ID=<your_chat_id>

# Interactive Brokers
IBKR_HOST=127.0.0.1
IBKR_PORT=4001                  # 4001 = paper  |  4002 = live
IBKR_CLIENT_ID=2                # different from 33-stock scheduler
IBKR_ACCOUNT_ID=DU1234567       # paper account id
IBKR_LIVE=true                  # true = allow IBKR connection (port decides account type)
```

### `.env.sector` (VM only) — sector-rotation systemd environment

```ini
MOMENTUM_DIR=/root/momentum
MOMENTUM_VENV=/root/momentum/.venv
SECTOR_NAV=330000               # your bucket 2 size in USD
SECTOR_MODE=simulate            # simulate | ibkr | dry_run
```

### `backend/config.py` key parameters (sector rotation section)

```python
SECTOR_ROTATION_LOOKBACK     = 12           # months (12-minus-1 momentum)
SECTOR_ROTATION_SKIP         = 1            # skip-last-month lag
SECTOR_ROTATION_TOP_K        = 3            # hold top-3 sectors

USE_SECTOR_TREND_FILTER      = True
SECTOR_TREND_MODE            = "abs_mom_12m"  # "abs_mom_12m" | "sma"

USE_SECTOR_ABSOLUTE_MOMENTUM = True
SECTOR_ABS_MOM_THRESHOLD     = 0.0           # sector must have positive momentum

# After-tax parameters (HK non-resident alien)
HK_NRA_DIVIDEND_WHT_US       = 0.30          # no US-HK treaty
HK_NRA_DIVIDEND_WHT_UCITS    = 0.15          # Ireland-US treaty inside ETF
HK_NRA_US_ESTATE_EXEMPTION   = 60_000.0
HK_NRA_US_ESTATE_EFFECTIVE   = 0.30
```

### UCITS ticker map (LSE USD share classes)

| Sector | UCITS Ticker | ISIN | Backtest Proxy |
|---|---|---|---|
| Information Technology | **IUIT** | IE00B3WJKG14 | XLK |
| Communication Services | **SXLC** | IE00BFWFPX50 | XLC |
| Consumer Discretionary | **IUCD** | IE00B4MCHD33 | XLY |
| Consumer Staples | **IUCS** | IE00B40B8R38 | XLP |
| Energy | **IUES** | IE00B42NKQ00 | XLE |
| Financials | **IUFS** | IE00B4JNQZ49 | XLF |
| Health Care | **IUHC** | IE00B43HR379 | XLV |
| Industrials | **IUIS** | IE00B4LN9N13 | XLI |
| Materials | **IUMS** | IE00B4LF7088 | XLB |
| Real Estate | **IUSP** | IE00B1FZS350 | XLRE |
| Utilities | **IUUS** | IE00B4KBBD01 | XLU |

---

## Deployment to VM (Vultr Ubuntu 24.04 via Tailscale)

Full runbook: [`deploy/DEPLOY_SECTOR_ROTATION.md`](deploy/DEPLOY_SECTOR_ROTATION.md)

**TL;DR:**

```bash
# On VM via SSH
cd /root/momentum && git pull origin master
./.venv/bin/pip install -U python-dotenv ib_insync apscheduler pytest pyarrow python-dateutil yfinance

# Verify
./.venv/bin/python -m pytest tests/test_sector_rotation.py tests/test_sector_executor.py -q
./.venv/bin/python sector_rotation_scheduler.py screener

# Configure
cp deploy/env.sector.example .env.sector
nano .env.sector   # set SECTOR_NAV and SECTOR_MODE

# Install systemd timer
sudo bash deploy/install_sector_rotation.sh

# Verify timer armed
systemctl list-timers sector-rotation.timer
```

Timer fires every **Friday 15:00 UTC (23:00 HKT)**. Wrapper script gates on
last-Friday-of-month (evaluated in **UTC** to match timer firing date).
Only actual last-Friday runs trigger the full rebalance.

---

## Monthly Operation

**Automated** via systemd timer on the VM:

| When | What |
|---|---|
| Every Friday 15:00 UTC | Timer fires |
| Non-last-Friday weeks | Gate rejects, exits in ~50ms |
| **Last Friday of month** | Full rebalance: screener → plan → execute (paper/IBKR) → DB write → Telegram ping |

**Manual override** (any day):

```bash
ssh root@vultr
cd /root/momentum && .venv/bin/python sector_rotation_scheduler.py rebalance --paper --nav 330000
```

---

## Transition Plan (current → live money)

Progression designed to de-risk incrementally; don't skip phases.

| Phase | When | `SECTOR_MODE` | `IBKR_PORT` | Account Type | What's being validated |
|---|---|---|---|---|---|
| 1 | Now → Apr 24 | `simulate` | n/a | none | Scheduler + gate + persistence + Telegram |
| 2 | May | `simulate` | n/a | none | Second cycle of strategy logic (signal unchanged or first rotation) |
| 3 | Jun | `ibkr` | `4001` | IBKR Paper | Contract specs + order routing + LSE permissions |
| 4 | Jul | `ibkr` | `4001` | IBKR Paper | Second paper cycle (verify fills match backtest) |
| 5 | Aug+ | `ibkr` | `4002` | **IBKR Live** | Real money (only after 2 clean paper cycles) |

---

## Testing

```bash
python -m pytest tests/ -v
```

Current test suite (17 tests, all passing as of `9699ba9`):

### `tests/test_sector_rotation.py` (10 tests)
- `test_compute_momentum_basic` — 12-1 formula correctness
- `test_compute_momentum_insufficient_history`
- `test_select_top_sectors_plain` — descending rank selection
- `test_select_top_sectors_absolute_threshold` — abs-momentum filter
- `test_select_top_sectors_handles_none`, `_handles_nan`
- `test_build_target_weights_top_k` — equal weighting
- `test_build_target_weights_partial_deployment`
- `test_build_target_weights_cash` — empty → all zeros
- `test_rebalance_dates_are_last_fridays`

### `tests/test_sector_executor.py` (7 tests)
- `test_empty_portfolio_deploy` — 3 BUYs from cash
- `test_same_target_no_trades` — idempotency
- `test_cash_signal_closes_all` — trend → cash
- `test_sector_rotation_one_swap` — sell outgoing, buy incoming
- `test_drift_threshold_skips_small_moves` — 5% band
- `test_cost_estimate_positive`
- `test_position_replay_survives_idempotent_runs` — **regression for commit `a6652bb` fix**

---

## Key Commits (sector-rotation track)

| Commit | Description |
|---|---|
| `99d0313` | Add UCITS sector rotation strategy (parallel track to 33-stock) |
| `378977d` | Add trend filter + after-tax metrics for HK NRA comparison |
| `18bab31` | Add Antonacci 12m abs-mom trend filter; set as default |
| `0c748db` | Automate scheduler: executor + IBKR contracts + CLI |
| `416766d` | Add Vultr VM deployment: systemd service+timer, install script, runbook |
| `4831689` | Fix timezone bug in last-Friday gate (use UTC to match timer) |
| `5c3f0b6` | Fire timer at 23:00 HKT (15:00 UTC) — just before LSE close |
| `a6652bb` | Fix position-reconstruction bug: replay all paper runs, not just latest |
| `9699ba9` | Add Telegram notifications for rebalance events |

---

## References

- **Antonacci, G. (2014).** *Dual Momentum Investing: An Innovative Strategy for Higher Returns with Lower Risk.* — Source of the 12-month absolute momentum trend filter currently used as default.
- **Faber, M. (2007).** *A Quantitative Approach to Tactical Asset Allocation.* — Original GTAA paper using 10-month SMA trend filter; compared against Antonacci in commit `18bab31`.
- **Asness, C., Moskowitz, T., Pedersen, L. (2013).** *Value and Momentum Everywhere.* — Standard 12-minus-1-month momentum formulation used for sector ranking.
- **Elton, E., Gruber, M., et al. (1996).** *Survivor bias and mutual fund performance.* — Methodology for quantifying survivorship bias in backtests.
- **Barroso, P., Santa-Clara, P. (2015).** *Momentum has its moments.* — Crash-protection vol-scaling framework used in the 33-stock strategy.

---

## Disclaimer

This code is for personal research and trading. Past backtest performance
does not guarantee future returns. Momentum strategies historically
experience sharp drawdowns during regime shifts; the Antonacci trend filter
mitigates but does not eliminate tail risk (observed max DD −30% in 2020
COVID fast-crash period).

Estate tax calculations assume a Hong Kong non-resident alien investor with
no US-HK tax treaty; they do not constitute legal or tax advice. Consult a
qualified professional before structuring your holdings for estate-tax
purposes.
