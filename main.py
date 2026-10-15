"""
ManusTrade Entry Point
"""

import sys
import logging
from src.config_manager import ConfigManager
from src.engine import TradingEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("manustrade.log", encoding="utf-8")
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
