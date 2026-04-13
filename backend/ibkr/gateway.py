"""
IB Gateway connection singleton.

In dry-run mode (IBKR_LIVE != 'true') no connection is attempted.
Set env vars in .env before enabling live mode:

    IBKR_HOST=127.0.0.1
    IBKR_PORT=4001         # 4001=paper  4002=live
    IBKR_CLIENT_ID=1
    IBKR_ACCOUNT_ID=UXXXXXXX
    IBKR_LIVE=false        # flip to true when credentials ready
"""
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config from environment ────────────────────────────────────
IBKR_HOST      = os.getenv("IBKR_HOST",      "127.0.0.1")
IBKR_PORT      = int(os.getenv("IBKR_PORT",  "4001"))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))
IBKR_LIVE      = os.getenv("IBKR_LIVE", "false").lower() == "true"

_ib = None  # global ib_insync.IB instance


def is_dry_run() -> bool:
    """Return True when running without live IBKR credentials."""
    return not IBKR_LIVE


def get_ib():
    """Return the active IB connection (None if dry-run)."""
    return _ib


def connect(timeout: int = 10):
    """
    Connect to IB Gateway / TWS.

    Safe to call multiple times — reuses existing connection.
    Raises RuntimeError if dry-run mode is active.
    """
    global _ib

    if is_dry_run():
        logger.info("[IBKR] Dry-run mode — skipping IB Gateway connection")
        return None

    try:
        from ib_insync import IB
    except ImportError:
        raise ImportError(
            "ib_insync is not installed. Run: pip install ib_insync"
        )

    if _ib and _ib.isConnected():
        logger.debug("[IBKR] Already connected")
        return _ib

    _ib = IB()
    logger.info(f"[IBKR] Connecting to {IBKR_HOST}:{IBKR_PORT} (clientId={IBKR_CLIENT_ID})...")
    _ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=timeout)
    logger.info("[IBKR] Connected to IB Gateway")
    return _ib


def disconnect():
    """Disconnect from IB Gateway if connected."""
    global _ib
    if _ib and _ib.isConnected():
        _ib.disconnect()
        logger.info("[IBKR] Disconnected from IB Gateway")
    _ib = None
