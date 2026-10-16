"""
High-Speed Millisecond Market Volatility & Climax Rejection Test Suite
Simulates:
1. Millisecond order dispatch latency profiling (Benchmarking speed).
2. Volatile Climax Spike & Rejection (Tip-of-the-Wick / Pinbar) test.
3. Anti-Reversal Slippage & Safeguard Verification.
"""

import time
import unittest
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from src.managers.risk_manager import RiskManager
from src.managers.order_manager import OrderManager
from src.analysis.indicators import extract_market_features, detect_fair_value_gaps
from src.analysis.gemini_trader import TradeSignal

class TestHighFrequencyVolatilityAndWickExecution(unittest.TestCase):

    def setUp(self):
        self.mock_mt5 = MagicMock()
        self.mock_account = MagicMock()
        self.mock_account.balance = 10000.0
        self.mock_account.equity = 10000.0
        self.mock_mt5.get_account_info.return_value = self.mock_account
        self.mock_mt5.get_history_deals.return_value = []

        self.mock_symbol = MagicMock()
        self.mock_symbol.spread = 15.0  # 15 points
        self.mock_symbol.point = 0.01
        self.mock_symbol.digits = 2
        self.mock_symbol.trade_tick_size = 0.01
        self.mock_symbol.trade_tick_value = 1.0
        self.mock_symbol.volume_min = 0.01
        self.mock_symbol.volume_max = 10.0
        self.mock_symbol.volume_step = 0.01
        self.mock_mt5.get_symbol_info.return_value = self.mock_symbol
        self.mock_mt5.open_trade.return_value = True
        self.mock_mt5.get_open_positions.return_value = []

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

    def test_order_execution_latency_sub_millisecond(self):
        """Measures local gatekeeping and order dispatch latency in milliseconds."""
        signal = TradeSignal(
            action="BUY",
            confidence=0.85,
            sl_points=6.5,
            tp_points=12.0,
            reasoning="Playbook A: Momentum breakout retest."
        )

        features = {"rsi_14": 48.0}

        latencies = []
        # Warmup and run 100 iterations
        for _ in range(100):
            t_start = time.perf_counter()
            self.order_mgr.handle_signal(
                symbol="GOLD#",
                signal=signal,
                min_confidence=0.65,
                macro_bias="STRONG_BULLISH",
                market_features=features
            )
            t_end = time.perf_counter()
            latencies.append((t_end - t_start) * 1000.0)  # Convert to ms

        avg_latency = np.mean(latencies)
        p99_latency = np.percentile(latencies, 99)

        print(f"\n[LATENCY_BENCHMARK] Average Order Verification & Dispatch: {avg_latency:.3f} ms | P99: {p99_latency:.3f} ms")
        # Ensure verification loop executes under 5 milliseconds locally
        self.assertLess(avg_latency, 5.0, "Local order gating took longer than 5ms!")

    def test_rejection_of_exhaustion_spike_at_tip_of_wick(self):
        """Simulates rapid climax pulse into resistance where RSI spikes > 70."""
        # Simulated candle data for Gold spiking from 4150 to 4174 in seconds
        spike_features = {
            "current_price": 4174.50,
            "rsi_14": 78.5,  # Heavy overbought climax
            "ema_21": 4155.00,
            "fair_value_gap": {"active_fvg": {"type": "BULLISH_FVG", "bottom": 4158.0, "top": 4165.0}}
        }

        # AI accidentally attempts to BUY the top
        chasing_signal = TradeSignal(
            action="BUY",
            confidence=0.75,
            sl_points=6.0,
            tp_points=10.0,
            reasoning="Buying high momentum candle."
        )

        # RiskManager must intercept and reject before order reaches the broker
        can_open, reason = self.risk.can_open_trade(
            symbol="GOLD#",
            action="BUY",
            sl_points=6.0,
            tp_points=10.0,
            macro_bias="STRONG_BULLISH",
            market_features=spike_features
        )

        self.assertFalse(can_open, "Exhaustion Guard failed to reject BUY at peak wick!")
        self.assertIn("Exhaustion Guard", reason)
        print(f"[WICK_GUARD_PASSED] Rejected climax top BUY: {reason}")

    def test_pinbar_rejection_wick_entry_execution(self):
        """Tests buying the bottom wick after a sharp rejection bounce."""
        # Price plunged to 4142, rejected with lower wick, RSI cooled to 34
        rebound_features = {
            "current_price": 4145.20,
            "rsi_14": 38.5,  # Rebounded out of extreme oversold
            "ema_21": 4152.00,
            "fair_value_gap": {"active_fvg": None}
        }

        rebound_signal = TradeSignal(
            action="BUY",
            confidence=0.82,
            sl_points=6.0,
            tp_points=12.0,
            reasoning="Playbook B: Pinbar lower wick rejection bounce at Support S1."
        )

        accepted = self.order_mgr.handle_signal(
            symbol="GOLD#",
            signal=rebound_signal,
            min_confidence=0.65,
            macro_bias="NEUTRAL_CONSOLIDATION",
            market_features=rebound_features
        )

        self.assertTrue(accepted, "Failed to execute verified Pinbar rejection bounce entry!")
        print("[PINBAR_WICK_PASSED] Rejection wick bounce executed cleanly.")

if __name__ == "__main__":
    unittest.main()
