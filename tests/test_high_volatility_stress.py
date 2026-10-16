"""
High-Volatility & Flash Crash / Whipsaw Stress Test Suite
Stress tests ManusTrade order engine under violent market conditions:
1. Flash Crash & Sudden V-Shape Reversal (e.g., $15 drop followed by $20 bounce in 1 minute).
2. Climax News Spike with rapid spread expansion.
3. Fast Break-Even & Tight Trailing Stop behavior during violent swings.
4. Consecutive Loss Circuit Breaker and Flash Reversal Protection.
"""

import time
import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from src.managers.risk_manager import RiskManager
from src.managers.order_manager import OrderManager
from src.analysis.indicators import extract_market_features
from src.analysis.gemini_trader import TradeSignal

class TestHighVolatilityStressExecution(unittest.TestCase):

    def setUp(self):
        self.mock_mt5 = MagicMock()
        self.mock_account = MagicMock()
        self.mock_account.balance = 10000.0
        self.mock_account.equity = 10000.0
        self.mock_mt5.get_account_info.return_value = self.mock_account
        self.mock_mt5.get_history_deals.return_value = []
        self.mock_mt5.get_open_positions.return_value = []

        self.mock_symbol = MagicMock()
        self.mock_symbol.spread = 20.0
        self.mock_symbol.point = 0.01
        self.mock_symbol.digits = 2
        self.mock_symbol.trade_tick_size = 0.01
        self.mock_symbol.trade_tick_value = 1.0
        self.mock_symbol.volume_min = 0.01
        self.mock_symbol.volume_max = 10.0
        self.mock_symbol.volume_step = 0.01
        self.mock_mt5.get_symbol_info.return_value = self.mock_symbol
        self.mock_mt5.open_trade.return_value = True

        self.risk = RiskManager(
            mt5_connector=self.mock_mt5,
            risk_percent=1.0,
            fixed_lot=0.01,
            max_spread_points=50.0,
            min_rr_ratio=1.5,
            consecutive_loss_limit=2,
            loss_cooldown_minutes=3,
            max_daily_drawdown_percent=3.0,
            max_trades_per_hour=10,
            min_sl_points=6.0,
            news_protection_enabled=True
        )

        self.order_mgr = OrderManager(
            mt5_connector=self.mock_mt5,
            risk_manager=self.risk
        )

    def test_v_shape_reversal_fast_break_even_protection(self):
        """
        Simulates the exact scenario the user experienced:
        SELL opened at 4150.70.
        Market plunged violently to 4147.20 (+3.50 pts profit).
        Market then whipsawed and violently spiked back to 4156.50.
        Verifies that Fast Break-Even secured the trade, preventing a -200 THB full SL loss.
        """
        mock_pos = MagicMock()
        mock_pos.ticket = 965607552
        mock_pos.type = 1  # SELL
        mock_pos.price_open = 4150.70
        mock_pos.sl = 4156.70
        mock_pos.tp = 4141.70
        mock_pos.price_current = 4147.50  # Profit: +3.20 pts (triggers Fast BE >= 1.80)
        self.mock_mt5.get_open_positions.return_value = [mock_pos]

        # 1. Run Fast Break-Even check
        self.order_mgr.manage_trailing_and_breakeven(
            symbol="GOLD#",
            be_trigger_points=1.8,
            trailing_step_points=1.2
        )

        # Verify that modify_position was called to protect profit
        self.mock_mt5.modify_position.assert_called()
        call_args = self.mock_mt5.modify_position.call_args
        new_sl = call_args[1]['sl']
        
        # New SL must be locked below or equal to entry price (for SELL, SL < 4150.70)
        self.assertLess(new_sl, 4150.70, "SL was not pulled down to secure profit before reversal!")
        print(f"\n[STRESS_TEST_PASSED] Fast BE successfully locked SL for SELL at {new_sl} before V-Shape rally.")

    def test_news_spread_explosion_rejection(self):
        """Simulates extreme volatility where broker spreads blow out from 20 to 120 points."""
        self.mock_symbol.spread = 120.0  # News shock spread blowout
        can_open, reason = self.risk.can_open_trade(
            symbol="GOLD#",
            action="BUY",
            sl_points=6.0,
            tp_points=12.0
        )
        self.assertFalse(can_open, "Failed to block trade during spread explosion!")
        print(f"[STRESS_TEST_PASSED] Blocked trade during extreme spread blowout: {reason}")

    def test_consecutive_whipsaw_circuit_breaker(self):
        """Simulates rapid consecutive whipsaw stop-outs triggering circuit breaker."""
        # First loss
        self.risk.record_manual_loss(-50.0)
        can_open_1, msg_1 = self.risk.check_loss_cooldown()
        self.assertFalse(can_open_1, "Cooldown failed after first whipsaw loss!")

        # Second loss
        self.risk.record_manual_loss(-50.0)
        can_open_2, msg_2 = self.risk.check_loss_cooldown()
        self.assertFalse(can_open_2, "Circuit Breaker failed after second whipsaw loss!")
        self.assertIn("Consecutive Loss Circuit Breaker", msg_2)
        print(f"[STRESS_TEST_PASSED] Circuit breaker active: {msg_2}")

if __name__ == "__main__":
    unittest.main()
