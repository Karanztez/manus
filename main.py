"""
ManusTrade Entry Point
"""

import os
import sys
import logging
from datetime import datetime
from src.config_manager import ConfigManager
from src.engine import TradingEngine

# Automatically create logs directory if it does not exist
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Generate unique log file for this specific session execution
session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
session_log_file = os.path.join(LOGS_DIR, f"run_{session_timestamp}.log")
latest_log_file = os.path.join(LOGS_DIR, "latest.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(session_log_file, encoding="utf-8"),
        logging.FileHandler(latest_log_file, mode="w", encoding="utf-8")
    ]
)
logger = logging.getLogger("ManusTrade.Main")

def main():
    try:
        config = ConfigManager.load("config.ini")
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)

    if not config.gemini.api_keys:
        logger.error("[CONFIG_ERROR] No Gemini API Keys found! Please set api_keys in config.ini or environment variable.")
        sys.exit(1)

    engine = TradingEngine(config)
    engine.start()

if __name__ == "__main__":
    main()
