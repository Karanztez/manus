"""
Risk Manager Module
Manages risk controls, max spread validation, and lot size calculations.
"""

import logging
from ..connectors.mt5_connector import MT5Connector

logger = logging.getLogger("ManusTrade.RiskManager")

class RiskManager:
    def __init__(
        self,
        mt5_connector: MT5Connector,
        risk_percent: float = 1.0,
        fixed_lot: float = 0.01,
        max_spread_points: float = 50.0,
        min_rr_ratio: float = 1.5
    ):
        self.mt5 = mt5_connector
        self.risk_percent = risk_percent
        self.fixed_lot = fixed_lot
        self.max_spread_points = max_spread_points
        self.min_rr_ratio = min_rr_ratio

    def is_spread_safe(self, symbol: str) -> bool:
        """Checks if current market spread is within safety limits."""
        info = self.mt5.get_symbol_info(symbol)
        if not info:
            return False
        
        spread = info.spread
        if spread > self.max_spread_points:
            logger.warning(f"Spread for {symbol} ({spread}) exceeds threshold ({self.max_spread_points}).")
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

    def calculate_lot(self, symbol: str, sl_points: float) -> float:
        """Calculates volume based on risk percentage or fixed lot setting."""
        if self.fixed_lot > 0:
            return self.fixed_lot

        account_info = self.mt5.get_account_info()
        symbol_info = self.mt5.get_symbol_info(symbol)
        
        if not account_info or not symbol_info or sl_points <= 0:
            return 0.01

        balance = account_info.balance
        risk_amount = balance * (self.risk_percent / 100.0)

        tick_value = symbol_info.trade_tick_value
        tick_size = symbol_info.trade_tick_size
        point = symbol_info.point

        if tick_size == 0 or point == 0:
            return 0.01

        loss_per_lot = (sl_points / point) * tick_value
        if loss_per_lot <= 0:
            return symbol_info.volume_min

        lot = risk_amount / loss_per_lot
        step = symbol_info.volume_step
        lot = round(lot / step) * step
        lot = max(symbol_info.volume_min, min(lot, symbol_info.volume_max))
        return round(lot, 2)
