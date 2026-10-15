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
            min_rr_ratio=config.risk.min_rr_ratio,
            consecutive_loss_limit=config.risk.consecutive_loss_limit,
            loss_cooldown_minutes=config.risk.loss_cooldown_minutes,
            max_daily_drawdown_percent=config.risk.max_daily_drawdown_percent,
            max_trades_per_hour=config.risk.max_trades_per_hour,
            min_sl_points=config.risk.min_sl_points,
            news_protection_enabled=config.risk.news_protection_enabled
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
                # 1. Manage Active Positions (Continuous Trailing Stop & Break-Even tuned for M1)
                self.order_manager.manage_trailing_and_breakeven(symbol, be_trigger_points=3.5, trailing_step_points=2.0)

                # 2. Risk Circuit Breakers & Cooldown Gate
                self.risk_manager.sync_deals_and_update_state()
                dd_ok, dd_msg = self.risk_manager.check_daily_drawdown()
                if not dd_ok:
                    time.sleep(10)
                    continue

                cooldown_ok, cooldown_msg = self.risk_manager.check_loss_cooldown()
                if not cooldown_ok:
                    time.sleep(5)
                    continue

                hourly_ok, hourly_msg = self.risk_manager.check_hourly_trade_limit()
                if not hourly_ok:
                    time.sleep(10)
                    continue

                # 3. Fetch Rates
                df = self.mt5.get_rates(symbol, timeframe, count=self.config.trading.history_bars)
                if df is None or len(df) < 30:
                    time.sleep(10)
                    continue

                current_candle_time = df['time'].iloc[-1]
                is_new_candle = (current_candle_time != last_candle_time)

                # Local Scanner: Disciplined M1 Triggers (No blind momentum chasing)
                local_trigger_reason = None
                latest_close = float(df['close'].iloc[-1])
                prev_close = float(df['close'].iloc[-2])
                price_delta = abs(latest_close - prev_close)

                # 3.1. New Candle Trigger (Safest for M1: complete wicks, fixed OHLC)
                if is_new_candle:
                    last_candle_time = current_candle_time
                    local_trigger_reason = f"New Candle ({current_candle_time})"
                
                # 3.2. Real-time Climax Spike Alert (Do NOT buy top / sell bottom)
                elif price_delta >= 35.0:
                    # In M1, sudden 35pt pulse is an exhaustion move. Wait for candle close / pullback.
                    if not hasattr(self, '_last_spike_alert') or (time.time() - self._last_spike_alert > 60):
                        self._last_spike_alert = time.time()
                        logger.info(f"[CLIMAX_SPIKE] Rapid pulse ({price_delta:.1f} pts). Awaiting candle close confirmation to prevent buying top/selling bottom.")

                # 3.3. Key Pivot Boundary Test (R1 / S1 mean-reversion test)
                last_completed = df.iloc[-2]
                from .tools import MathTools, WebTools, ChartTools
                pivots = MathTools.calculate_pivot_points(float(last_completed['high']), float(last_completed['low']), float(last_completed['close']))
                if not is_new_candle and (latest_close >= pivots['r1'] or latest_close <= pivots['s1']):
                    if not hasattr(self, '_last_pivot_alert') or (time.time() - self._last_pivot_alert > 30):
                        self._last_pivot_alert = time.time()
                        local_trigger_reason = f"Testing Pivot Boundary (R1={pivots['r1']}, S1={pivots['s1']})"

                # 4. If trigger detected, dispatch to Gemini AI
                if local_trigger_reason:
                    logger.info(f"[LOCAL_SCANNER_TRIGGER] Reason: {local_trigger_reason} | Price: {latest_close}")

                    # Check spread safety
                    if not self.risk_manager.is_spread_safe(symbol):
                        time.sleep(2)
                        continue

                    # News Shield: Check high-impact news before dispatching
                    web_news = WebTools.search_news(f"{symbol} gold price market news", max_results=2)
                    if self.config.risk.news_protection_enabled:
                        has_news, news_desc = WebTools.detect_high_impact_news(web_news)
                        if has_news:
                            logger.warning(f"[NEWS_SHIELD_ACTIVE] {news_desc}. Pausing trade entry to avoid whipsaw.")
                            time.sleep(10)
                            continue

                    # Extract Indicators & Math Tools
                    features = extract_market_features(df)
                    features['pivot_points'] = pivots

                    # Multi-Timeframe Confluence Tool (M1, M5, M15, H1)
                    from .tools import MultiTimeframeScanner
                    mtf_data = MultiTimeframeScanner.get_multi_tf_confluence(self.mt5, symbol)
                    features['multi_timeframe_alignment'] = mtf_data
                    logger.info(f"[MULTI_TF_SCAN] Macro Bias: {mtf_data['macro_bias']}")

                    # Spatial Chart Matrix
                    chart_visual = ChartTools.render_ascii_chart(df, width=35, height=8)

                    # Capture Real HD Screenshot from MT5
                    import os
                    screenshot_file = os.path.join(os.getcwd(), f"chart_{symbol}_{timeframe}.png")
                    has_screenshot = self.mt5.save_chart_screenshot(symbol, timeframe, screenshot_file, width=800, height=450)
                    active_img_path = screenshot_file if has_screenshot and os.path.exists(screenshot_file) else None

                    pos_summary = self.order_manager.get_position_summary(symbol)

                    # Gemini Multi-modal Analysis with Memory, Vision Screenshot & Local Context
                    signal = self.ai_trader.analyze(
                        symbol=symbol,
                        timeframe=timeframe,
                        market_data=features,
                        current_position=pos_summary,
                        chart_visual=chart_visual,
                        web_context=web_news,
                        local_scan_note=local_trigger_reason,
                        image_path=active_img_path
                    )
                    if signal:
                        self.order_manager.handle_signal(
                            symbol=symbol,
                            signal=signal,
                            min_confidence=self.config.trading.min_confidence,
                            macro_bias=mtf_data['macro_bias']
                        )

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
