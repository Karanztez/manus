"""
ManusTrade Realtime Bridge
Reads live account & market data from local XM MT5 and pushes to Cloud Web Dashboard.
"""
import time
import json
import logging
import MetaTrader5 as mt5
from src.config_manager import ConfigManager
import urllib.request

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ManusTrade.Bridge")

def push_to_vps():
    config = ConfigManager.load("config.ini")
    symbol = config.trading.symbol
    logger.info(f"Connecting to Local MT5 for {config.mt5.login} on {config.mt5.server}...")
    
    if not mt5.initialize():
        logger.error(f"MT5 Init failed: {mt5.last_error()}")
        return

    account_info = mt5.account_info()
    if not account_info:
        logger.error("Could not fetch account info.")
        return

    logger.info(f"[SUCCESS] Connected to REAL Account: {account_info.login} | Balance: {account_info.balance} {account_info.currency}")
    
    vps_url = "https://mt.eiei.love/api/status"
    logger.info(f"Streaming data to VPS Dashboard at {vps_url}...")

    while True:
        try:
            acc = mt5.account_info()
            tick = mt5.symbol_info_tick(symbol)
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 60)
            
            candles = []
            if rates is not None and len(rates) > 0:
                for r in rates:
                    candles.append({
                        "time": int(r['time']),
                        "open": float(r['open']),
                        "high": float(r['high']),
                        "low": float(r['low']),
                        "close": float(r['close']),
                    })

            payload = {
                "account": {
                    "login": acc.login,
                    "server": acc.server,
                    "balance": acc.balance,
                    "equity": acc.equity,
                    "currency": acc.currency,
                    "leverage": acc.leverage
                },
                "market": {
                    "symbol": symbol,
                    "bid": tick.bid if tick else 0.0,
                    "ask": tick.ask if tick else 0.0,
                    "spread": round((tick.ask - tick.bid) * 100, 1) if tick else 0,
                    "candles": candles
                }
            }

            req = urllib.request.Request(
                "http://157.85.101.53:3496/api/sync",
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'}
            )
            try:
                urllib.request.urlopen(req, timeout=3)
            except Exception:
                pass

            time.sleep(2)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Sync loop error: {e}")
            time.sleep(3)

if __name__ == "__main__":
    push_to_vps()
