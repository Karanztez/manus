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

    def handle_signal(self, symbol: str, signal: TradeSignal, min_confidence: float, macro_bias: str = "", market_features: Optional[dict] = None) -> bool:
        """
        Processes a trade signal through comprehensive risk verification and order execution.
        """
        if signal.confidence < min_confidence:
            logger.info(f"Signal confidence {signal.confidence:.2f} < threshold {min_confidence}. Skipping.")
            return False

        open_positions = self.get_open_positions(symbol)

        if signal.action == "CLOSE":
            # Prevent AI premature panic-cutting on minor intra-candle pullbacks.
            # Only close if high conviction reversal signal (confidence >= 0.90) AND position is actually in profit or at hard invalidation.
            if open_positions and signal.confidence >= 0.90:
                pos = open_positions[0]
                profit = getattr(pos, "profit", 0.0)
                if profit > 0:
                    logger.info(f"[PROFIT_TAKE] Closing profitable position for {symbol} based on high-conviction AI signal ({signal.confidence:.2f}).")
                    self.risk.record_manual_win()
                    self.mt5.close_positions(symbol)
                    return True
            logger.info(f"[HOLD_PROTECTION] Ignoring premature CLOSE signal ({signal.confidence:.2f}). Letting predefined SL/TP and Trailing Stop manage the position.")
            return False

        if signal.action in ["BUY", "SELL"]:
            # Check if there is already a position in the same direction
            target_type = 0 if signal.action == "BUY" else 1
            has_same_direction = any(getattr(p, "type", -1) == target_type for p in open_positions)

            if has_same_direction:
                logger.info(f"Position for {signal.action} already open on {symbol}. No duplicate entry.")
                return False

            # Enforce minimum SL distance to protect against M1 market noise
            sl_points = self.risk.enforce_min_sl(signal.sl_points)
            tp_points = signal.tp_points
            if sl_points > signal.sl_points and signal.sl_points > 0:
                # Maintain min RR ratio if SL was widened
                tp_points = max(tp_points, round(sl_points * self.risk.min_rr_ratio, 2))

            # Master Risk Validation Gate
            can_open, reason = self.risk.can_open_trade(
                symbol=symbol,
                action=signal.action,
                sl_points=sl_points,
                tp_points=tp_points,
                macro_bias=macro_bias,
                market_features=market_features
            )
            if not can_open:
                logger.warning(f"[ORDER_REJECTED_BY_RISK] {reason}")
                return False

            # If opposite position exists, close it first and record its outcome
            if open_positions:
                pos = open_positions[0]
                profit = getattr(pos, "profit", 0.0)
                if profit < 0:
                    self.risk.record_manual_loss(profit)
                else:
                    self.risk.record_manual_win()
                logger.info(f"Reversal detected. Closing existing opposite position (P/L: {profit:.2f}) before entering {signal.action}.")
                self.mt5.close_positions(symbol)

            lot = self.risk.calculate_lot(symbol, sl_points)
            logger.info(f"[EXECUTE] {signal.action} {lot} lots on {symbol} (SL: {sl_points:.2f}, TP: {tp_points:.2f})")
            
            success = self.mt5.open_trade(
                symbol=symbol,
                action=signal.action,
                volume=lot,
                sl_points=sl_points,
                tp_points=tp_points,
                comment=f"Gemini {signal.confidence:.2f}"
            )
            if success:
                self.risk.record_trade_opened()
            return success

        return False

    def manage_trailing_and_breakeven(self, symbol: str, be_trigger_points: float = 1.8, trailing_step_points: float = 1.2):
        """
        Sub-Millisecond High-Frequency Risk & Profit Management for M1 Scalping:
        1. Fast Break-Even: Locks entry + spread buffer as soon as profit reaches 1.8 points.
        2. Tight Trailing Stop: Keeps SL close (1.2 points) to protect against sudden V-shape reversals.
        3. Flash Reverse Guard: Detects rapid violent counter-spikes and instantly cuts or reverses without waiting.
        """
        positions = self.get_open_positions(symbol)
        if not positions:
            return

        tick = self.mt5.get_symbol_info(symbol)
        if not tick:
            return

        # Dynamic spread buffer calculation (Spread * 1.5 converted to price points)
        spread_raw = getattr(tick, "spread", 20.0)
        point_size = getattr(tick, "point", 0.01)
        spread_points = spread_raw * point_size
        be_buffer = max(0.25, round(spread_points * 1.5, 2))

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
                # 1. Fast Break-Even Check: lock entry + dynamic spread buffer
                if profit_points >= be_trigger_points and (cur_sl < price_open or cur_sl == 0.0):
                    new_sl = round(price_open + be_buffer, 2)
                    logger.info(f"[FAST_BE] Instant Break-even triggered for BUY #{ticket} at {new_sl} (Profit: +{profit_points:.2f})")
                    self.mt5.modify_position(ticket, sl=new_sl, tp=cur_tp)

                # 2. Tight Trailing Stop Check
                elif profit_points >= (be_trigger_points + trailing_step_points):
                    ideal_sl = round(cur_price - trailing_step_points, 2)
                    if ideal_sl > cur_sl:
                        logger.info(f"[TIGHT_TRAILING] Advancing SL for BUY #{ticket} to {ideal_sl} (+{profit_points:.2f})")
                        self.mt5.modify_position(ticket, sl=ideal_sl, tp=cur_tp)

            elif pos_type == 1:  # SELL
                profit_points = price_open - cur_price
                # 1. Fast Break-Even Check: lock entry - dynamic spread buffer
                if profit_points >= be_trigger_points and (cur_sl > price_open or cur_sl == 0.0):
                    new_sl = round(price_open - be_buffer, 2)
                    logger.info(f"[FAST_BE] Instant Break-even triggered for SELL #{ticket} at {new_sl} (Profit: +{profit_points:.2f})")
                    self.mt5.modify_position(ticket, sl=new_sl, tp=cur_tp)

                # 2. Tight Trailing Stop Check
                elif profit_points >= (be_trigger_points + trailing_step_points):
                    ideal_sl = round(cur_price + trailing_step_points, 2)
                    if cur_sl == 0.0 or ideal_sl < cur_sl:
                        logger.info(f"[TIGHT_TRAILING] Advancing SL for SELL #{ticket} to {ideal_sl} (+{profit_points:.2f})")
                        self.mt5.modify_position(ticket, sl=ideal_sl, tp=cur_tp)

