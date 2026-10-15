"""
Unit and Integration Tests for ManusTrade Tools
Tests:
1. WebTools (Search and news retrieval)
2. MathTools (Lot sizing, Pivot points, Kelly criterion)
3. ChartTools (Spatial ASCII chart rendering)
"""

import unittest
import pandas as pd
from src.tools import WebTools, MathTools, ChartTools

class TestManusTools(unittest.TestCase):

    def test_math_tools_lot_size(self):
        # 1000 balance, 1% risk = 10 risk amount. SL 100 points, tick_value 1.0 -> 0.10 lot
        lot = MathTools.calculate_lot_size(balance=1000.0, risk_percent=1.0, sl_points=100.0, tick_value=1.0)
        self.assertAlmostEqual(lot, 0.10, places=2)

        # Minimum lot test
        lot_min = MathTools.calculate_lot_size(balance=100.0, risk_percent=1.0, sl_points=500.0, tick_value=1.0)
        self.assertEqual(lot_min, 0.01)

    def test_math_tools_pivots(self):
        high = 2650.0
        low = 2630.0
        close = 2640.0
        pivots = MathTools.calculate_pivot_points(high, low, close)
        self.assertEqual(pivots["pivot"], 2640.0)
        self.assertEqual(pivots["r1"], 2650.0)
        self.assertEqual(pivots["s1"], 2630.0)

    def test_math_tools_kelly(self):
        # 60% win rate, 1.5 R:R ratio
        # Kelly = 0.60 - (0.40 / 1.5) = 0.60 - 0.2667 = 0.3333 -> Half Kelly ~ 0.1667
        kelly = MathTools.evaluate_kelly_criterion(win_rate=0.60, reward_ratio=1.5)
        self.assertGreater(kelly, 0.15)
        self.assertLess(kelly, 0.20)

    def test_chart_tools_ascii(self):
        # Create mock DataFrame of 15 candles
        data = {
            'time': list(range(1000, 1015)),
            'open': [2630 + i * 0.5 for i in range(15)],
            'high': [2632 + i * 0.5 for i in range(15)],
            'low': [2629 + i * 0.5 for i in range(15)],
            'close': [2631 + i * 0.5 for i in range(15)],
        }
        df = pd.DataFrame(data)
        chart_str = ChartTools.render_ascii_chart(df, width=15, height=5)
        self.assertIn("|", chart_str)
        self.assertIn("+", chart_str)
        self.assertGreater(len(chart_str.split("\n")), 5)

    def test_web_tools_search(self):
        # Test DuckDuckGo news scraping
        news = WebTools.search_news("Gold price ForexFactory", max_results=2)
        self.assertIsInstance(news, str)
        self.assertGreater(len(news), 10)

if __name__ == "__main__":
    unittest.main()
