"""
ManusTrade Web Gateway
Lightweight IPC / Socket Server bridging Node.js Web Dashboard with Python MT5 & Gemini Engine.
"""

import os
import sys
import json
import time
import socket
import threading
import logging
from typing import Dict, Any

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.config_manager import ConfigManager
from src.engine import TradingEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("ManusTrade.Gateway")

class WebGateway:
    def __init__(self, host: str = "127.0.0.1", port: int = 9999):
        self.host = host
        self.port = port
        self.server_socket = None
        self.client_socket = None
        self.is_running = False
        
        config_path = os.path.join(BASE_DIR, "config.ini")
        self.config = ConfigManager.load(config_path)
        self.engine = TradingEngine(self.config)
        self.engine_thread = None

    def start(self):
        self.is_running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        logger.info(f"[GATEWAY_ONLINE] IPC Server listening on {self.host}:{self.port}")

        # Connect to MT5 on startup so web dashboard gets immediate data
        if not self.engine.mt5.connected:
            self.engine.mt5.connect()

        # Start background status broadcaster
        threading.Thread(target=self._broadcast_loop, daemon=True).start()

        # Accept client connections
        while self.is_running:
            try:
                client, addr = self.server_socket.accept()
                logger.info(f"[CLIENT_CONNECTED] Node.js Dashboard connected from {addr}")
                self.client_socket = client
                threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()
            except Exception as e:
                if self.is_running:
                    logger.error(f"[ERROR] Accept error: {e}")
                break

    def _handle_client(self, client: socket.socket):
        buffer = ""
        while self.is_running:
            try:
                data = client.recv(4096).decode('utf-8')
                if not data:
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self._process_command(json.loads(line.strip()), client)
            except Exception as e:
                logger.warning(f"[CLIENT_DISCONNECTED] Client socket closed: {e}")
                break

    def _process_command(self, cmd: Dict[str, Any], client: socket.socket):
        action = cmd.get("action")
        logger.info(f"[COMMAND_RECEIVED] {action}")

        if action == "START_BOT":
            if not self.engine.is_running:
                self.engine_thread = threading.Thread(target=self.engine.start, daemon=True)
                self.engine_thread.start()
                self._send_to_client(client, {"status": "OK", "message": "Trading engine started"})

        elif action == "STOP_BOT":
            if self.engine.is_running:
                self.engine.stop()
                self._send_to_client(client, {"status": "OK", "message": "Trading engine stopped"})

        elif action == "CLOSE_ALL":
            symbol = self.config.trading.symbol
            closed = self.engine.mt5.close_positions(symbol)
            self._send_to_client(client, {"status": "OK", "message": f"Closed {closed} positions"})

        elif action == "SET_TIMEFRAME":
            new_tf = cmd.get("timeframe", "M15").upper()
            if new_tf in ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]:
                self.config.trading.timeframe = new_tf
                logger.info(f"[TIMEFRAME_CHANGED] Switched timeframe to {new_tf}")
                self._send_to_client(client, {"status": "OK", "message": f"Timeframe changed to {new_tf}"})

        elif action == "TRIGGER_SIGNAL":
            symbol = self.config.trading.symbol
            tf = self.config.trading.timeframe
            rates_df = self.engine.mt5.get_rates(symbol, tf, count=self.config.trading.history_bars)
            if rates_df is not None and len(rates_df) >= 20:
                from src.analysis.indicators import extract_market_features
                from src.tools import MathTools, WebTools, ChartTools
                features = extract_market_features(rates_df)
                last_row = rates_df.iloc[-2]
                features['pivot_points'] = MathTools.calculate_pivot_points(float(last_row['high']), float(last_row['low']), float(last_row['close']))
                chart_visual = ChartTools.render_ascii_chart(rates_df, width=35, height=8)
                web_news = WebTools.search_news(f"{symbol} gold price news", max_results=3)
                pos_summary = self.engine.order_manager.get_position_summary(symbol)

                signal = self.engine.ai_trader.analyze(
                    symbol=symbol,
                    timeframe=tf,
                    market_data=features,
                    current_position=pos_summary,
                    chart_visual=chart_visual,
                    web_context=web_news
                )
                if signal:
                    # Execute trade if confidence passes
                    self.engine.order_manager.handle_signal(symbol, signal, self.config.trading.min_confidence)
                    self._send_to_client(client, {
                        "status": "OK",
                        "action": "SIGNAL_RESULT",
                        "data": {
                            "action": signal.action,
                            "confidence": signal.confidence,
                            "sl_points": signal.sl_points,
                            "tp_points": signal.tp_points,
                            "reasoning": signal.reasoning
                        }
                    })
                else:
                    self._send_to_client(client, {"status": "ERROR", "message": "AI analysis returned no signal"})
            else:
                self._send_to_client(client, {"status": "ERROR", "message": "Insufficient candle data for analysis"})

        elif action == "GET_STATUS":
            status = self._collect_status()
            self._send_to_client(client, {"type": "STATUS_UPDATE", "data": status})

    def _collect_status(self) -> Dict[str, Any]:
        connector = self.engine.mt5
        is_init = connector.connected
        acc = connector.get_account_info() if is_init else None
        symbol = self.config.trading.symbol
        current_tf_str = self.config.trading.timeframe.upper()
        
        positions = connector.get_open_positions(symbol) if is_init else []
        
        pos_list = []
        for p in positions:
            pos_list.append({
                "ticket": getattr(p, "ticket", 10001),
                "type": "BUY" if getattr(p, "type", 0) == 0 else "SELL",
                "volume": getattr(p, "volume", 0.01),
                "price_open": getattr(p, "price_open", 2650.0),
                "sl": getattr(p, "sl", 0.0),
                "tp": getattr(p, "tp", 0.0),
                "profit": round(getattr(p, "profit", 0.0), 2)
            })

        # Fetch recent order history deals (Past 7 days)
        history_deals = []
        try:
            from src.connectors.mt5_connector import HAS_MT5
            if HAS_MT5 and is_init:
                import MetaTrader5 as mt5
                from_t = time.time() - 86400 * 7
                to_t = time.time() + 86400
                deals = mt5.history_deals_get(from_t, to_t)
                if deals:
                    for d in reversed(deals):
                        if d.symbol:
                            deal_action = "BUY" if d.type == 0 else ("SELL" if d.type == 1 else "OTHER")
                            history_deals.append({
                                "ticket": d.ticket,
                                "order": d.order,
                                "symbol": d.symbol,
                                "type": deal_action,
                                "volume": d.volume,
                                "price": d.price,
                                "profit": round(d.profit, 2),
                                "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d.time))
                            })
        except Exception:
            pass

        # Fetch recent candles for interactive chart based on selected timeframe
        candles = []
        rates_df = connector.get_rates(symbol, current_tf_str, count=80)
        if rates_df is not None and not rates_df.empty:
            for _, r in rates_df.iterrows():
                t_val = int(r['time'].timestamp()) if hasattr(r['time'], 'timestamp') else int(r['time'])
                candles.append({
                    "time": t_val,
                    "open": float(r['open']),
                    "high": float(r['high']),
                    "low": float(r['low']),
                    "close": float(r['close']),
                })

        last_close = candles[-1]["close"] if candles else 2650.0
        bid = last_close
        ask = round(last_close + 0.25, 2)

        return {
            "engine_running": self.engine.is_running,
            "connected": is_init,
            "timeframe": current_tf_str,
            "account": {
                "login": getattr(acc, "login", "N/A"),
                "server": getattr(acc, "server", "XMGlobal-MT5"),
                "balance": getattr(acc, "balance", 10000.0),
                "equity": getattr(acc, "equity", 10000.0),
                "currency": getattr(acc, "currency", "USD"),
                "leverage": getattr(acc, "leverage", 100)
            },
            "market": {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "spread": round((ask - bid) * 100, 1),
                "candles": candles
            },
            "positions": pos_list,
            "history": history_deals[:15],
            "model": self.config.gemini.model_name
        }

    def _send_to_client(self, client: socket.socket, payload: Dict[str, Any]):
        try:
            msg = json.dumps(payload) + "\n"
            client.sendall(msg.encode('utf-8'))
        except Exception:
            pass

    def _send_response(self, payload: Dict[str, Any]):
        if self.client_socket:
            self._send_to_client(self.client_socket, payload)

    def _broadcast_loop(self):
        while self.is_running:
            time.sleep(2)
            if self.client_socket:
                status = self._collect_status()
                self._send_response({"type": "STATUS_UPDATE", "data": status})

if __name__ == "__main__":
    try:
        gateway = WebGateway()
        gateway.start()
    except Exception as e:
        logger.exception(f"[FATAL] Gateway crashed on startup: {e}")
        import traceback
        traceback.print_exc()
    except KeyboardInterrupt:
        logger.info("Gateway terminated.")
