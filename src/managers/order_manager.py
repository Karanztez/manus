"""
Order Manager Module
Responsible for position tracking, opening, closing, and order state management.
"""

import logging
from typing import Optional, List
from ..connectors.mt5_connector import MT5Connector
from ..analysis.gemini_trader import TradeSignal
from .risk_manager import RiskManager

logger = logging.getLogger("ManusTrade.OrderManager")

class OrderManager:
    def __init__(self, mt5_connector: MT5Connector, risk_manager: RiskManager):
        self.mt5 = mt5_connector
        self.risk = risk_manager

    def get_open_positions(self, symbol: str) -> List:
        return self.mt5.get_open_positions(symbol)

    def get_position_summary(self, symbol: str) -> Optional[str]:
        positions = self.get_open_positions(symbol)
        if not positions:
            return None
        pos = positions[0]
        pos_type = "BUY" if pos.type == 0 else "SELL"
        return f"{pos_type} #{pos.ticket} (Open: {pos.price_open}, Profit: {pos.profit})"

    def handle_signal(self, symbol: str, signal: TradeSignal, min_confidence: float) -> bool:
        """
        Processes a trade signal through risk verification and order execution.
        """
        if signal.confidence < min_confidence:
            logger.info(f"Signal confidence {signal.confidence:.2f} < threshold {min_confidence}. Skipping.")
            return False

        open_positions = self.get_open_positions(symbol)

        if signal.action == "CLOSE":
            if open_positions:
                logger.info(f"Closing all open positions for {symbol} based on AI signal.")
                self.mt5.close_positions(symbol)
                return True
            return False

        if signal.action in ["BUY", "SELL"]:
            # Check if there is already a position in the same direction
            target_type = 0 if signal.action == "BUY" else 1
            has_same_direction = any(p.type == target_type for p in open_positions)

            if has_same_direction:
                logger.info(f"Position for {signal.action} already open on {symbol}. No duplicate entry.")
                return False

            # If opposite position exists, close it first
            if open_positions:
                logger.info(f"Reversal detected. Closing existing opposite position before entering {signal.action}.")
                self.mt5.close_positions(symbol)

            # Risk & RR validation
            if not self.risk.validate_rr_ratio(signal.sl_points, signal.tp_points):
                logger.warning("Trade rejected due to poor Risk/Reward ratio.")
                return False

            lot = self.risk.calculate_lot(symbol, signal.sl_points)
            logger.info(f"[EXECUTE] {signal.action} {lot} lots on {symbol} (SL: {signal.sl_points}, TP: {signal.tp_points})")
            
            return self.mt5.open_trade(
                symbol=symbol,
                action=signal.action,
                volume=lot,
                sl_points=signal.sl_points,
                tp_points=signal.tp_points,
                comment=f"Gemini {signal.confidence:.2f}"
            )

        return False
