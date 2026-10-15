"""
Trading Engine / Coordinator
Integrates config, connector, analysis, and managers into a cohesive loop.
"""

import time
import logging
from typing import Optional
from .config_manager import AppConfig
from .connectors.mt5_connector import MT5Connector
from .analysis.indicators import extract_market_features
from .analysis.gemini_trader import GeminiTrader
from .managers.risk_manager import RiskManager
from .managers.order_manager import OrderManager

logger = logging.getLogger("ManusTrade.Engine")

class TradingEngine:
    def __init__(self, config: AppConfig):
        self.config = config
        self.mt5 = MT5Connector(magic_number=config.trading.magic_number)
        self.ai_trader = GeminiTrader(
            api_keys=config.gemini.api_keys,
            model_name=config.gemini.model_name
        )
        self.risk_manager = RiskManager(
            mt5_connector=self.mt5,
            risk_percent=config.risk.risk_percent,
            fixed_lot=config.risk.fixed_lot,
            max_spread_points=config.risk.max_spread_points,
            min_rr_ratio=config.risk.min_rr_ratio
        )
        self.order_manager = OrderManager(
            mt5_connector=self.mt5,
            risk_manager=self.risk_manager
        )
        self.is_running = False

    def start(self):
        """Starts the main trading cycle."""
        if not self.mt5.connect():
            logger.error("Failed to connect to MetaTrader 5.")
            return

        self.is_running = True
        symbol = self.config.trading.symbol
        timeframe = self.config.trading.timeframe
        last_candle_time = None

        logger.info(f"[ENGINE_START] Symbol: {symbol} | TF: {timeframe} | Model: {self.config.gemini.model_name}")

        try:
            while self.is_running:
                df = self.mt5.get_rates(symbol, timeframe, count=self.config.trading.history_bars)
                if df is None or len(df) < 30:
                    time.sleep(10)
                    continue

                current_candle_time = df['time'].iloc[-1]

                if current_candle_time != last_candle_time:
                    last_candle_time = current_candle_time
                    logger.info(f"[NEW_CANDLE] Time: {current_candle_time} | Inspecting market...")

                    # Check spread safety
                    if not self.risk_manager.is_spread_safe(symbol):
                        time.sleep(10)
                        continue

                    # Extract Indicators & Math Tools
                    features = extract_market_features(df)
                    
                    # Math Tool: Quant Pivot Points
                    last_row = df.iloc[-2]  # Completed candle
                    from .tools import MathTools, WebTools, ChartTools
                    pivots = MathTools.calculate_pivot_points(float(last_row['high']), float(last_row['low']), float(last_row['close']))
                    features['pivot_points'] = pivots

                    # Tools: Spatial Chart Matrix & Web News
                    chart_visual = ChartTools.render_ascii_chart(df, width=35, height=8)
                    web_news = WebTools.search_news(f"{symbol} gold price market news", max_results=3)

                    pos_summary = self.order_manager.get_position_summary(symbol)

                    # Gemini Multi-modal Analysis
                    signal = self.ai_trader.analyze(
                        symbol=symbol,
                        timeframe=timeframe,
                        market_data=features,
                        current_position=pos_summary,
                        chart_visual=chart_visual,
                        web_context=web_news
                    )
                    if signal:
                        self.order_manager.handle_signal(symbol, signal, self.config.trading.min_confidence)

                # Continuous Trailing Stop & Break-Even Evaluation (every 5 seconds)
                self.order_manager.manage_trailing_and_breakeven(symbol, be_trigger_points=80.0, trailing_step_points=40.0)

                time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Bot execution interrupted by user.")
        finally:
            self.stop()

    def stop(self):
        """Stops the engine and shuts down MT5."""
        self.is_running = False
        self.mt5.shutdown()
        logger.info("Trading Engine stopped cleanly.")
