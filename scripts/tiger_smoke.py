#!/usr/bin/env python3
"""Tiger credential smoke test — verify Tiger API credentials against PAPER environment.

Usage:
    python scripts/tiger_smoke.py

Exit codes:
    0 — Connection successful, credentials valid
    1 — Connection failed or credential missing
"""

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path so config/ and src/ are importable
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# Logging: stdout, minimal format
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("tiger_smoke")


def main() -> int:
    # ------------------------------------------------------------------
    # 1. Load credentials from pydantic BaseSettings (.env)
    # ------------------------------------------------------------------
    try:
        from config.settings import settings
    except ImportError as e:
        logger.error("Cannot import config.settings — is PYTHONPATH set correctly? %s", e)
        return 1

    if not settings.has_tiger_creds:
        logger.error(
            "TIGER_* credentials incomplete in .env. "
            "Required: TIGER_PRIVATE_KEY, TIGER_TIGER_ID, TIGER_ACCOUNT, "
            "TIGER_TOKEN, TIGER_LICENSE"
        )
        return 1

    tiger_id_masked = settings.TIGER_TIGER_ID[:4] + "****"
    logger.info("TIGER_TIGER_ID=%s  TIGER_ENV=%s", tiger_id_masked, settings.TIGER_ENV)

    # ------------------------------------------------------------------
    # 2. Build minimal AppConfig — force PAPER (simulated) environment
    # ------------------------------------------------------------------
    try:
        from src.trading.config import AppConfig, TigerConfig

        tiger_cfg = TigerConfig(environment="PAPER")
        config = AppConfig(tiger=tiger_cfg)
    except ImportError as e:
        logger.error("Cannot import AppConfig/TigerConfig: %s", e)
        return 1

    # ------------------------------------------------------------------
    # 3. Connect via TigerClient
    # ------------------------------------------------------------------
    try:
        from src.trading.tiger_client import TigerClient

        client = TigerClient(config)
        logger.info("Calling TigerClient.connect() ...")
        client.connect()

        if not client.is_connected:
            logger.error("TigerClient reported not connected after connect()")
            return 1

        logger.info("TigerClient connected successfully")
    except Exception as e:
        logger.error("TigerClient.connect() failed: %s", e)
        return 1

    # ------------------------------------------------------------------
    # 4. Read-only check: get_assets (account summary)
    # ------------------------------------------------------------------
    try:
        assets = client.get_assets()
        if assets:
            logger.info(
                "Account summary: net_value=%s, cash=%s, buying_power=%s",
                assets.get("net_value", "N/A"),
                assets.get("cash", "N/A"),
                assets.get("buying_power", "N/A"),
            )
        else:
            logger.warning("get_assets() returned empty — account may have no positions")
    except Exception as e:
        logger.error("get_assets() failed: %s", e)
        return 1

    # ------------------------------------------------------------------
    # 5. Clean disconnect
    # ------------------------------------------------------------------
    try:
        client.disconnect()
    except Exception as e:
        logger.warning("disconnect() warning: %s", e)

    logger.info("Tiger connection OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
