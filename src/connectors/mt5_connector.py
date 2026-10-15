"""
MT5 Connector Module for ManusTrade
Handles connection, data fetching, and order execution with MetaTrader 5 Terminal.
"""

import logging
from typing import Optional, List, Any
import pandas as pd
import time
import random

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    mt5 = None
    HAS_MT5 = False

logger = logging.getLogger("ManusTrade.MT5")

if HAS_MT5:
    TIMEFRAME_MAP = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
else:
    TIMEFRAME_MAP = {
        "M1": 1,
        "M5": 5,
        "M15": 15,
        "M30": 30,
        "H1": 60,
        "H4": 240,
        "D1": 1440,
    }

class MockAccountInfo:
    login = 108074548
    server = "XMGlobal-MT5 (Simulated/Linux)"
    balance = 10000.0
    equity = 10000.0
    currency = "USD"
    trade_allowed = True

class MockSymbolInfo:
    digits = 2
    point = 0.01

class MockTick:
    def __init__(self, price=2650.50):
        self.ask = price + 0.25
        self.bid = price
        self.time = int(time.time())

class MT5Connector:
    def __init__(self, magic_number: int = 888999):
        self.magic_number = magic_number
        self.connected = False
        self.simulated_positions = []
        self._last_price = 2650.0

    def connect(self) -> bool:
        """Initialize connection to MetaTrader 5 terminal."""
        if not HAS_MT5:
            logger.info("MetaTrader5 C-extension not available on Linux. Running in High-Fidelity Simulation/Gateway Mode.")
            self.connected = True
            return True

        if not mt5.initialize():
            logger.error(f"MT5 initialize failed: {mt5.last_error()}")
            return False
        
        terminal_info = mt5.terminal_info()
        if not terminal_info.trade_allowed:
            logger.warning("Trade is not allowed in MT5 Terminal settings! Check 'Allow Algo Trading'.")

        account_info = mt5.account_info()
        if account_info is not None:
            logger.info(f"Connected to MT5 Account: {account_info.login} ({account_info.server}) | Balance: {account_info.balance} {account_info.currency}")
            self.connected = True
            return True
        else:
            logger.error("Failed to retrieve MT5 account info.")
            return False

    def shutdown(self):
        """Disconnect and shutdown MT5."""
        if HAS_MT5:
            mt5.shutdown()
        self.connected = False
        logger.info("MT5 connection closed.")

    def get_rates(self, symbol: str, timeframe_str: str, count: int = 50) -> Optional[pd.DataFrame]:
        """Fetch historical candlestick data."""
        if not HAS_MT5:
            now = int(time.time())
            rates = []
            cur_price = self._last_price
            for i in range(count, 0, -1):
                t = now - (i * 60)
                move = (random.random() - 0.49) * 2.0
                o = cur_price
                c = cur_price + move
                h = max(o, c) + random.random() * 1.5
                l = min(o, c) - random.random() * 1.5
                cur_price = c
                rates.append({
                    "time": t,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "tick_volume": random.randint(10, 200)
                })
            self._last_price = cur_price
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df

        tf = TIMEFRAME_MAP.get(timeframe_str.upper(), mt5.TIMEFRAME_M15)
        
        if not mt5.symbol_select(symbol, True):
            logger.error(f"Failed to select symbol {symbol} in Market Watch.")
            return None

        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is None or len(rates) == 0:
            logger.error(f"Failed to fetch rates for {symbol}: {mt5.last_error()}")
            return None

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df

    def get_symbol_info(self, symbol: str) -> Optional[Any]:
        """Get trading information of the symbol."""
        if not HAS_MT5:
            return MockSymbolInfo()
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol {symbol} not found.")
            return None
        return info

    def get_account_info(self) -> Optional[Any]:
        """Get account information."""
        if not HAS_MT5:
            return MockAccountInfo()
        return mt5.account_info()

    def get_open_positions(self, symbol: Optional[str] = None) -> List[Any]:
        """Get open positions filtered by magic number and symbol."""
        if not HAS_MT5:
            return self.simulated_positions

        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()

        if positions is None:
            return []
        
        return [p for p in positions if p.magic == self.magic_number]

    def open_trade(
        self,
        symbol: str,
        action: str,
        volume: float,
        sl_points: float = 0.0,
        tp_points: float = 0.0,
        comment: str = "Gemini Trade"
    ) -> bool:
        """
        Execute Buy or Sell market order.
        sl_points / tp_points: distance in price units/points.
        """
        info = self.get_symbol_info(symbol)
        if not info:
            return False

        if not HAS_MT5:
            ticket = random.randint(100000000, 999999999)
            logger.info(f"[SIMULATED] Order {action} {volume} lots executed for {symbol} at {self._last_price} (Ticket #{ticket})")
            return True

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"Failed to get current tick for {symbol}")
            return False

        action_type = action.upper()
        if action_type == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            sl = price - sl_points if sl_points > 0 else 0.0
            tp = price + tp_points if tp_points > 0 else 0.0
        elif action_type == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            sl = price + sl_points if sl_points > 0 else 0.0
            tp = price - tp_points if tp_points > 0 else 0.0
        else:
            logger.warning(f"Unsupported action: {action}")
            return False

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": round(sl, info.digits) if sl > 0 else 0.0,
            "tp": round(tp, info.digits) if tp > 0 else 0.0,
            "deviation": 20,
            "magic": self.magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed [retcode={result.retcode}]: {result.comment}")
            return False

        logger.info(f"Order executed successfully! Deal: {result.deal}, Ticket: {result.order}")
        return True

    def close_positions(self, symbol: str, position_type: Optional[str] = None) -> int:
        """Close open positions for this symbol."""
        if not HAS_MT5:
            count = len(self.simulated_positions)
            self.simulated_positions = []
            logger.info(f"[SIMULATED] Closed {count} positions.")
            return count

        positions = self.get_open_positions(symbol)
        closed_count = 0
        for pos in positions:
            if position_type:
                if position_type.upper() == "BUY" and pos.type != mt5.POSITION_TYPE_BUY:
                    continue
                if position_type.upper() == "SELL" and pos.type != mt5.POSITION_TYPE_SELL:
                    continue

            tick = mt5.symbol_info_tick(symbol)
            close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            close_price = tick.bid if pos.type == mt5.POSITION_TYPE_BUY else tick.ask

            req = {
                "action": mt5.TRADE_ACTION_DEAL,
                "position": pos.ticket,
                "symbol": symbol,
                "volume": pos.volume,
                "type": close_type,
                "price": close_price,
                "deviation": 20,
                "magic": self.magic_number,
                "comment": "Gemini Close",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            if res.retcode == mt5.TRADE_RETCODE_DONE:
                closed_count += 1
                logger.info(f"Position #{pos.ticket} closed successfully.")
            else:
                logger.error(f"Failed to close position #{pos.ticket}: {res.comment}")

        return closed_count

    def modify_position(self, ticket: int, sl: float, tp: float) -> bool:
        """Modify Stop Loss and Take Profit of an existing position."""
        if not HAS_MT5:
            for p in self.simulated_positions:
                if getattr(p, "ticket", None) == ticket:
                    p.sl = sl
                    p.tp = tp
                    logger.info(f"[SIMULATED] Position #{ticket} modified SL={sl}, TP={tp}")
                    return True
            return False

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": round(sl, 2),
            "tp": round(tp, 2)
        }
        res = mt5.order_send(request)
        if res.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[POSITION_MODIFIED] Ticket #{ticket} SL updated to {sl}, TP={tp}")
            return True
        else:
            logger.error(f"[MODIFY_FAILED] Ticket #{ticket} failed: {res.comment}")
            return False
