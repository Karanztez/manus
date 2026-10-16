"""
Risk Manager Module
Manages risk controls, max spread validation, lot size calculations,
loss cooldowns, daily drawdown limits, and multi-timeframe direction guards.
"""

import time
import logging
from datetime import datetime
from typing import Tuple, Optional, List
from ..connectors.mt5_connector import MT5Connector

logger = logging.getLogger("ManusTrade.RiskManager")

class RiskManager:
    def __init__(
        self,
        mt5_connector: MT5Connector,
        risk_percent: float = 1.0,
        fixed_lot: float = 0.01,
        max_spread_points: float = 50.0,
        min_rr_ratio: float = 1.5,
        consecutive_loss_limit: int = 2,
        loss_cooldown_minutes: int = 10,
        max_daily_drawdown_percent: float = 3.0,
        max_trades_per_hour: int = 4,
        min_sl_points: float = 6.0,
        news_protection_enabled: bool = True,
        max_spread_crypto: float = 2500.0
    ):
        self.mt5 = mt5_connector
        self.risk_percent = risk_percent
        self.fixed_lot = fixed_lot
        self.max_spread_points = max_spread_points
        self.max_spread_crypto = max_spread_crypto
        self.min_rr_ratio = min_rr_ratio
        self.consecutive_loss_limit = consecutive_loss_limit
        self.loss_cooldown_minutes = loss_cooldown_minutes
        self.max_daily_drawdown_percent = max_daily_drawdown_percent
        self.max_trades_per_hour = max_trades_per_hour
        self.min_sl_points = min_sl_points
        self.news_protection_enabled = news_protection_enabled

        # Dynamic State Tracking
        self.initial_daily_balance: Optional[float] = None
        self.initial_daily_date: Optional[str] = None
        self.consecutive_losses: int = 0
        self.last_loss_time: float = 0.0
        self.recent_trade_timestamps: List[float] = []
        self._processed_deal_tickets: set = set()

    def sync_deals_and_update_state(self):
        """Scans recent closed deals from MT5 to update consecutive losses and PnL."""
        deals = self.mt5.get_history_deals(hours=24)
        if not deals:
            return

        for d in deals:
            ticket = getattr(d, "ticket", None)
            if ticket and ticket not in self._processed_deal_tickets:
                self._processed_deal_tickets.add(ticket)
                profit = getattr(d, "profit", 0.0)
                deal_time = getattr(d, "time", time.time())
                deal_symbol = getattr(d, "symbol", "GOLD#")
                deal_type = getattr(d, "type", 0)
                action_str = "BUY" if deal_type == 0 else "SELL"

                # Persist to TradeJournal for AI self-reflection
                try:
                    from ..memory.trade_journal import TradeJournal
                    journal = TradeJournal()
                    journal.record_trade_result(
                        symbol=deal_symbol,
                        action=action_str,
                        profit=profit,
                        reason=f"Closed Deal #{ticket}"
                    )
                except Exception as ex:
                    logger.debug(f"Could not record deal to journal: {ex}")

                if profit < 0:
                    self.consecutive_losses += 1
                    self.last_loss_time = deal_time
                    logger.warning(f"[RISK_UPDATE] Closed trade #{ticket} recorded LOSS: {profit:.2f}. Consecutive losses: {self.consecutive_losses}")
                elif profit > 0:
                    self.consecutive_losses = 0
                    logger.info(f"[RISK_UPDATE] Closed trade #{ticket} recorded PROFIT: +{profit:.2f}. Consecutive losses reset to 0.")

    def check_daily_drawdown(self) -> Tuple[bool, str]:
        """Validates that today's account drawdown has not breached the daily risk limit."""
        account_info = self.mt5.get_account_info()
        if not account_info:
            return True, ""

        today_str = datetime.now().strftime("%Y-%m-%d")
        if self.initial_daily_date != today_str or self.initial_daily_balance is None:
            self.initial_daily_date = today_str
            self.initial_daily_balance = account_info.balance
            logger.info(f"[DAILY_EQUITY_RESET] Starting balance for {today_str}: {self.initial_daily_balance:.2f}")

        equity = getattr(account_info, "equity", account_info.balance)
        if self.initial_daily_balance > 0:
            drawdown_amount = self.initial_daily_balance - equity
            drawdown_pct = (drawdown_amount / self.initial_daily_balance) * 100.0
            if drawdown_pct >= self.max_daily_drawdown_percent:
                msg = f"Daily Drawdown Breached: -{drawdown_pct:.2f}% (Limit: {self.max_daily_drawdown_percent:.2f}%). Trading stopped for the day."
                now = time.time()
                if not hasattr(self, '_last_dd_log') or (now - self._last_dd_log >= 300):
                    self._last_dd_log = now
                    logger.error(f"[CIRCUIT_BREAKER] {msg}")
                return False, msg

        return True, ""

    def check_loss_cooldown(self) -> Tuple[bool, str]:
        """Enforces a resting cooldown period after losing trades to prevent whipsaw revenge trading."""
        now = time.time()
        should_log = not hasattr(self, '_last_cooldown_log') or (now - self._last_cooldown_log >= 60)

        if self.consecutive_losses >= self.consecutive_loss_limit:
            # Extended cooldown for consecutive losses
            cooldown_seconds = self.loss_cooldown_minutes * 60 * 2
            elapsed = now - self.last_loss_time
            if elapsed < cooldown_seconds:
                remaining_m = max(1, int((cooldown_seconds - elapsed) / 60))
                msg = f"Consecutive Loss Circuit Breaker ({self.consecutive_losses} losses). Paused for {remaining_m} more minutes."
                if should_log:
                    self._last_cooldown_log = now
                    logger.warning(f"[COOLDOWN_ACTIVE] {msg}")
                return False, msg

        elif self.consecutive_losses > 0:
            cooldown_seconds = self.loss_cooldown_minutes * 60
            elapsed = now - self.last_loss_time
            if elapsed < cooldown_seconds:
                remaining_m = max(1, int((cooldown_seconds - elapsed) / 60))
                msg = f"Post-Loss Cooldown active. Paused for {remaining_m} more minutes to let market stabilize."
                if should_log:
                    self._last_cooldown_log = now
                    logger.warning(f"[COOLDOWN_ACTIVE] {msg}")
                return False, msg

        return True, ""

    def check_hourly_trade_limit(self) -> Tuple[bool, str]:
        """Throttles trading frequency to prevent M1 churn and overtrading."""
        now = time.time()
        self.recent_trade_timestamps = [t for t in self.recent_trade_timestamps if now - t < 3600]
        if len(self.recent_trade_timestamps) >= self.max_trades_per_hour:
            msg = f"Hourly trade cap reached ({len(self.recent_trade_timestamps)}/{self.max_trades_per_hour} trades in last hour). Throttling."
            logger.warning(f"[FREQUENCY_CAP] {msg}")
            return False, msg
        return True, ""

    def validate_mtf_rule(self, action: str, macro_bias: str) -> Tuple[bool, str]:
        """Strictly forbids trading against higher timeframe macro trend on M1."""
        action = action.upper()
        bias = macro_bias.upper()

        if action == "BUY" and "BEARISH" in bias:
            msg = f"MTF Conflict: Cannot BUY on M1 while Macro Bias is Bearish ({macro_bias})."
            logger.warning(f"[MTF_FILTER] {msg}")
            return False, msg

        if action == "SELL" and "BULLISH" in bias:
            msg = f"MTF Conflict: Cannot SELL on M1 while Macro Bias is Bullish ({macro_bias})."
            logger.warning(f"[MTF_FILTER] {msg}")
            return False, msg

        if "CONFLICTED" in bias or "MIXED" in bias:
            msg = f"MTF Conflict: Macro Bias is Conflicted/Whipsaw. Rejecting {action} on M1."
            logger.warning(f"[MTF_FILTER] {msg}")
            return False, msg

        return True, ""

    def is_spread_safe(self, symbol: str) -> bool:
        """
        Checks if current market spread is within safety limits.
        Dynamically applies Crypto-specific threshold (e.g. BTCUSD# / ETHUSD#)
        vs standard Forex/Gold threshold.
        """
        info = self.mt5.get_symbol_info(symbol)
        if not info:
            return False
        
        spread = getattr(info, "spread", 0.0)
        symbol_upper = symbol.upper()

        is_crypto = any(c in symbol_upper for c in ["BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"])
        threshold = self.max_spread_crypto if is_crypto else self.max_spread_points

        if spread > threshold:
            category = "Crypto" if is_crypto else "Standard"
            logger.warning(f"Spread for {symbol} ({spread} pts) exceeds {category} threshold ({threshold} pts).")
            return False
        return True

    def validate_rr_ratio(self, sl_points: float, tp_points: float) -> bool:
        """Validates that Risk to Reward ratio meets minimum requirement."""
        if sl_points <= 0:
            return True
        ratio = tp_points / sl_points
        if ratio < self.min_rr_ratio:
            logger.warning(f"Risk to Reward ratio ({ratio:.2f}) is below minimum requirement ({self.min_rr_ratio}).")
            return False
        return True

    def enforce_min_sl(self, sl_points: float) -> float:
        """Enforces minimum Stop Loss distance to prevent 1-minute noise triggers."""
        if sl_points < self.min_sl_points:
            logger.info(f"[SL_GUARD] Widening tight SL from {sl_points:.1f} to minimum safety floor {self.min_sl_points:.1f} pts.")
            return self.min_sl_points
        return sl_points

    def record_trade_opened(self):
        """Records timestamp of newly opened trade for hourly throttling."""
        self.recent_trade_timestamps.append(time.time())

    def record_manual_loss(self, loss_amount: float = -1.0):
        """Explicitly flags a loss outcome when detected by order manager."""
        self.consecutive_losses += 1
        self.last_loss_time = time.time()
        logger.warning(f"[RISK_TRIGGER] Loss recorded manually ({loss_amount:.2f}). Consecutive losses: {self.consecutive_losses}")

    def record_manual_win(self):
        """Resets consecutive loss counter upon profitable exit."""
        self.consecutive_losses = 0

    def can_open_trade(
        self,
        symbol: str,
        action: str,
        sl_points: float,
        tp_points: float,
        macro_bias: str = "",
        market_features: Optional[dict] = None
    ) -> Tuple[bool, str]:
        """
        Master gatekeeper: verifies spread, drawdown, cooldown, frequency, MTF, and RR.
        """
        self.sync_deals_and_update_state()

        # 1. Spread Check
        if not self.is_spread_safe(symbol):
            return False, f"Spread exceeds max limit ({self.max_spread_points})."

        # 2. Daily Drawdown Check
        safe, msg = self.check_daily_drawdown()
        if not safe:
            return False, msg

        # 3. Loss Cooldown Check
        safe, msg = self.check_loss_cooldown()
        if not safe:
            return False, msg

        # 4. Hourly Frequency Cap
        safe, msg = self.check_hourly_trade_limit()
        if not safe:
            return False, msg

        # 5. Multi-Timeframe Alignment
        if macro_bias:
            safe, msg = self.validate_mtf_rule(action, macro_bias)
            if not safe:
                return False, msg

        # 6. Multi-Timeframe Overextension / Exhaustion Check (H1 -> M15 -> M5 -> M1)
        if market_features:
            mtf_info = market_features.get("multi_timeframe_alignment", {})
            macro_exhaustion = mtf_info.get("macro_exhaustion", "")
            rsi = market_features.get("rsi_14", 50.0)

            # Rule A: If Macro (H1 or M15) is Overbought, forbid BUY on M1 even if M1 has dipped slightly
            if action == "BUY" and "MACRO_OVERBOUGHT" in macro_exhaustion:
                logger.warning(f"[MACRO_EXHAUSTION_GUARD] Rejecting BUY: Higher TFs (H1/M15) are Overbought. High probability of major dump.")
                return False, "Macro Exhaustion Guard: Higher timeframes (H1/M15) are Overbought. Do not BUY tops."

            # Rule B: If Macro (H1 or M15) is Oversold, forbid SELL on M1
            if action == "SELL" and "MACRO_OVERSOLD" in macro_exhaustion:
                logger.warning(f"[MACRO_EXHAUSTION_GUARD] Rejecting SELL: Higher TFs (H1/M15) are Oversold. High probability of strong bounce.")
                return False, "Macro Exhaustion Guard: Higher timeframes (H1/M15) are Oversold. Do not SELL bottoms."

            # Rule C: Local M1 exhaustion floor / ceiling
            if action == "BUY" and rsi > 70.0:
                logger.warning(f"[EXHAUSTION_GUARD] Rejecting BUY: M1 RSI-14 is {rsi:.1f} (Overbought climax). Do not chase tops.")
                return False, f"Exhaustion Guard: M1 RSI-14 ({rsi:.1f}) is Overbought. Wait for pullback."
            elif action == "SELL" and rsi < 30.0:
                logger.warning(f"[EXHAUSTION_GUARD] Rejecting SELL: M1 RSI-14 is {rsi:.1f} (Oversold floor). Do not chase bottoms.")
                return False, f"Exhaustion Guard: M1 RSI-14 ({rsi:.1f}) is Oversold. Wait for pullback."

        # 7. Risk-to-Reward Ratio
        if not self.validate_rr_ratio(sl_points, tp_points):
            return False, f"Risk to Reward ratio below minimum requirement ({self.min_rr_ratio})."

        return True, "Trade approved by RiskManager."

    def calculate_lot(self, symbol: str, sl_points: float) -> float:
        """Calculates volume based on risk percentage or fixed lot setting."""
        if self.fixed_lot > 0:
            return self.fixed_lot

        account_info = self.mt5.get_account_info()
        symbol_info = self.mt5.get_symbol_info(symbol)
        
        if not account_info or not symbol_info or sl_points <= 0:
            return 0.01

        balance = getattr(account_info, "balance", 1000.0)
        risk_amount = balance * (self.risk_percent / 100.0)

        tick_value = getattr(symbol_info, "trade_tick_value", 1.0)
        tick_size = getattr(symbol_info, "trade_tick_size", 0.01)
        point = getattr(symbol_info, "point", 0.01)

        if tick_size == 0 or point == 0:
            return 0.01

        loss_per_lot = (sl_points / point) * tick_value
        if loss_per_lot <= 0:
            return getattr(symbol_info, "volume_min", 0.01)

        lot = risk_amount / loss_per_lot
        step = getattr(symbol_info, "volume_step", 0.01)
        lot = round(lot / step) * step
        vol_min = getattr(symbol_info, "volume_min", 0.01)
        vol_max = getattr(symbol_info, "volume_max", 100.0)
        lot = max(vol_min, min(lot, vol_max))
        return round(lot, 2)

