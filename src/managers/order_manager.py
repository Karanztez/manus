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

    def manage_trailing_and_breakeven(self, symbol: str, be_trigger_points: float = 100.0, trailing_step_points: float = 50.0):
        """
        Automated Risk Management:
        1. Break-Even: Move SL to entry price once in profit >= be_trigger_points.
        2. Trailing Stop: Stepwise trailing of Stop Loss to lock in profits as market advances.
        """
        positions = self.get_open_positions(symbol)
        if not positions:
            return

        tick = self.mt5.get_symbol_info(symbol)
        if not tick:
            return

        for p in positions:
            ticket = getattr(p, "ticket", None)
            pos_type = getattr(p, "type", 0)  # 0: BUY, 1: SELL
            price_open = getattr(p, "price_open", 0.0)
            cur_sl = getattr(p, "sl", 0.0)
            cur_tp = getattr(p, "tp", 0.0)
            
            # Current price
            cur_price = getattr(p, "price_current", 0.0)
            if cur_price == 0.0:
                continue

            if pos_type == 0:  # BUY
                profit_points = cur_price - price_open
                # 1. Break-Even Check
                if profit_points >= be_trigger_points and cur_sl < price_open:
                    new_sl = round(price_open + 5.0, 2)  # Entry + small buffer
                    logger.info(f"[BREAK_EVEN] Moving SL to Breakeven for BUY #{ticket} ({new_sl})")
                    self.mt5.modify_position(ticket, sl=new_sl, tp=cur_tp)

                # 2. Trailing Stop Check
                elif profit_points >= (be_trigger_points + trailing_step_points):
                    ideal_sl = round(cur_price - trailing_step_points, 2)
                    if ideal_sl > cur_sl:
                        logger.info(f"[TRAILING_STOP] Stepping SL for BUY #{ticket} to {ideal_sl}")
                        self.mt5.modify_position(ticket, sl=ideal_sl, tp=cur_tp)

            elif pos_type == 1:  # SELL
                profit_points = price_open - cur_price
                # 1. Break-Even Check
                if profit_points >= be_trigger_points and (cur_sl == 0.0 or cur_sl > price_open):
                    new_sl = round(price_open - 5.0, 2)  # Entry - small buffer
                    logger.info(f"[BREAK_EVEN] Moving SL to Breakeven for SELL #{ticket} ({new_sl})")
                    self.mt5.modify_position(ticket, sl=new_sl, tp=cur_tp)

                # 2. Trailing Stop Check
                elif profit_points >= (be_trigger_points + trailing_step_points):
                    ideal_sl = round(cur_price + trailing_step_points, 2)
                    if cur_sl == 0.0 or ideal_sl < cur_sl:
                        logger.info(f"[TRAILING_STOP] Stepping SL for SELL #{ticket} to {ideal_sl}")
                        self.mt5.modify_position(ticket, sl=ideal_sl, tp=cur_tp)
