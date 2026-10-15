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
                is_new_candle = (current_candle_time != last_candle_time)

                # Local Fast Scanner (Checks every loop: Breakouts, Volatility Spikes, Key Levels)
                local_trigger_reason = None
                latest_close = float(df['close'].iloc[-1])
                prev_close = float(df['close'].iloc[-2])
                price_delta = abs(latest_close - prev_close)

                # 1. New Candle Trigger
                if is_new_candle:
                    last_candle_time = current_candle_time
                    local_trigger_reason = f"New Candle ({current_candle_time})"
                
                # 2. Real-time Spike Trigger (Price moves >= 35 points in a single pulse)
                elif price_delta >= 35.0:
                    local_trigger_reason = f"Momentum Spike ({price_delta:.1f} pts change)"

                # 3. Key Pivot Breakout Trigger
                last_completed = df.iloc[-2]
                from .tools import MathTools, WebTools, ChartTools
                pivots = MathTools.calculate_pivot_points(float(last_completed['high']), float(last_completed['low']), float(last_completed['close']))
                if not is_new_candle and (latest_close >= pivots['r1'] or latest_close <= pivots['s1']):
                    # Cooldown mechanism: only trigger once per 15s for pivot test
                    if not hasattr(self, '_last_pivot_alert') or (time.time() - self._last_pivot_alert > 20):
                        self._last_pivot_alert = time.time()
                        local_trigger_reason = f"Testing Pivot Boundary (R1={pivots['r1']}, S1={pivots['s1']})"

                # If trigger detected, dispatch to Gemini AI
                if local_trigger_reason:
                    logger.info(f"[LOCAL_SCANNER_TRIGGER] Reason: {local_trigger_reason} | Price: {latest_close}")

                    # Check spread safety
                    if not self.risk_manager.is_spread_safe(symbol):
                        time.sleep(2)
                        continue

                    # Extract Indicators & Math Tools
                    features = extract_market_features(df)
                    features['pivot_points'] = pivots

                    # Tools: Spatial Chart Matrix & Web News
                    chart_visual = ChartTools.render_ascii_chart(df, width=35, height=8)
                    web_news = WebTools.search_news(f"{symbol} gold price market news", max_results=2)

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

                # Continuous Trailing Stop & Break-Even Evaluation (runs every 2 seconds)
                self.order_manager.manage_trailing_and_breakeven(symbol, be_trigger_points=60.0, trailing_step_points=30.0)

                # High-speed local loop tick (2 seconds)
                time.sleep(2)
        except KeyboardInterrupt:
            logger.info("Bot execution interrupted by user.")
        finally:
            self.stop()

    def stop(self):
        """Stops the engine and shuts down MT5."""
        self.is_running = False
        self.mt5.shutdown()
        logger.info("Trading Engine stopped cleanly.")
