"""
Unit Tests for RiskManager & M1 Scalping Protections
Verifies:
1. Daily Drawdown Guard (Passes Prop Firm limits)
2. Loss Cooldown & Consecutive Loss Circuit Breaker
3. Hourly Frequency Throttling (Overtrading prevention)
4. Multi-Timeframe Trend Alignment Rule
5. Minimum SL Noise Floor
6. High-Impact News Keyword Detection
"""

import time
import unittest
from unittest.mock import MagicMock
from src.managers.risk_manager import RiskManager
from src.tools import WebTools

class TestRiskManagerM1(unittest.TestCase):

    def setUp(self):
        self.mock_mt5 = MagicMock()
        self.mock_account = MagicMock()
        self.mock_account.balance = 10000.0
        self.mock_account.equity = 10000.0
        self.mock_mt5.get_account_info.return_value = self.mock_account
        self.mock_mt5.get_history_deals.return_value = []

        self.mock_symbol = MagicMock()
        self.mock_symbol.spread = 15.0
        self.mock_symbol.point = 0.01
        self.mock_symbol.trade_tick_size = 0.01
        self.mock_symbol.trade_tick_value = 1.0
        self.mock_symbol.volume_min = 0.01
        self.mock_symbol.volume_max = 10.0
        self.mock_symbol.volume_step = 0.01
        self.mock_mt5.get_symbol_info.return_value = self.mock_symbol

        self.risk = RiskManager(
            mt5_connector=self.mock_mt5,
            risk_percent=1.0,
            fixed_lot=0.01,
            max_spread_points=50.0,
            min_rr_ratio=1.5,
            consecutive_loss_limit=2,
            loss_cooldown_minutes=10,
            max_daily_drawdown_percent=3.0,
            max_trades_per_hour=4,
            min_sl_points=6.0,
            news_protection_enabled=True
        )

    def test_daily_drawdown_guard(self):
        # 1. Normal state: equity == balance -> safe
        safe, msg = self.risk.check_daily_drawdown()
        self.assertTrue(safe)

        # 2. Drawdown of 2% (equity 9800 on 10000) -> safe
        self.mock_account.equity = 9800.0
        safe, msg = self.risk.check_daily_drawdown()
        self.assertTrue(safe)

        # 3. Drawdown of 3.5% (equity 9650 on 10000) -> breached!
        self.mock_account.equity = 9650.0
        safe, msg = self.risk.check_daily_drawdown()
        self.assertFalse(safe)
        self.assertIn("Daily Drawdown Breached", msg)

    def test_loss_cooldown_and_consecutive_breaker(self):
        # Initial: no losses
        safe, _ = self.risk.check_loss_cooldown()
        self.assertTrue(safe)

        # 1 loss recorded
        self.risk.record_manual_loss(-50.0)
        self.assertEqual(self.risk.consecutive_losses, 1)
        safe, msg = self.risk.check_loss_cooldown()
        self.assertFalse(safe)
        self.assertIn("Post-Loss Cooldown", msg)

        # 2 consecutive losses -> Breaker
        self.risk.record_manual_loss(-30.0)
        self.assertEqual(self.risk.consecutive_losses, 2)
        safe, msg = self.risk.check_loss_cooldown()
        self.assertFalse(safe)
        self.assertIn("Consecutive Loss Circuit Breaker", msg)

        # Reset upon win
        self.risk.record_manual_win()
        self.assertEqual(self.risk.consecutive_losses, 0)
        safe, _ = self.risk.check_loss_cooldown()
        self.assertTrue(safe)

    def test_hourly_frequency_cap(self):
        for _ in range(4):
            self.risk.record_trade_opened()

        safe, msg = self.risk.check_hourly_trade_limit()
        self.assertFalse(safe)
        self.assertIn("Hourly trade cap reached", msg)

    def test_mtf_rule_validation(self):
        # Reject BUY when Bearish
        safe, msg = self.risk.validate_mtf_rule("BUY", "STRONG_BEARISH (Safe to SHORT rallies)")
        self.assertFalse(safe)
        self.assertIn("Cannot BUY on M1", msg)

        # Reject SELL when Bullish
        safe, msg = self.risk.validate_mtf_rule("SELL", "STRONG_BULLISH (Safe to BUY dips)")
        self.assertFalse(safe)
        self.assertIn("Cannot SELL on M1", msg)

        # Reject when conflicted / whipsaw
        safe, msg = self.risk.validate_mtf_rule("BUY", "CONFLICTED / MIXED (High risk of whipsaw)")
        self.assertFalse(safe)
        self.assertIn("Conflicted/Whipsaw", msg)

        # Allow BUY when Bullish
        safe, msg = self.risk.validate_mtf_rule("BUY", "STRONG_BULLISH (Safe to BUY dips)")
        self.assertTrue(safe)

    def test_min_sl_enforcement(self):
        # Tight 2.5 point SL should be widened to 6.0
        widened = self.risk.enforce_min_sl(2.5)
        self.assertEqual(widened, 6.0)

        # 8.0 point SL should remain 8.0
        preserved = self.risk.enforce_min_sl(8.0)
        self.assertEqual(preserved, 8.0)

    def test_news_detection(self):
        news = "US Retail Sales beat expectations while Wholesale PPI jumps 1.3%"
        has_news, desc = WebTools.detect_high_impact_news(news)
        self.assertTrue(has_news)
        self.assertIn("RETAIL SALES", desc)
        self.assertIn("PPI", desc)

        normal = "Gold price consolidates in quiet afternoon trading"
        has_news, _ = WebTools.detect_high_impact_news(normal)
        self.assertFalse(has_news)

if __name__ == "__main__":
    unittest.main()
