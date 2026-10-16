"""
ManusTrade Tools Module
Provides tools for:
1. Web Search / Financial News Scraping (Economic Calendar, CPI, Fed Rates, Geopolitics)
2. Mathematical Calculations (Compound Interest, Kelly Criterion, Position Sizing, Risk/Reward, Pivot Points)
3. Chart Visualization / Image Rendering for Gemini Vision Analysis
"""

import os
import re
import math
import logging
import urllib.request
import urllib.parse
from typing import Dict, Any, Optional

logger = logging.getLogger("ManusTrade.Tools")

# =====================================================================
# 1. Web Search & Financial News Tool
# =====================================================================
class WebTools:
    """Safe, lightweight web search and financial news extraction without browser bloat."""

    @staticmethod
    def search_news(query: str = "Gold price news ForexFactory", max_results: int = 5) -> str:
        """
        Searches web or financial feeds for gold and market sentiment.
        Uses DuckDuckGo HTML API for fast, zero-key scraping.
        """
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                html = response.read().decode("utf-8", errors="ignore")

            # Extract snippets using regex
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.DOTALL)
            clean_snippets = []
            for s in snippets[:max_results]:
                text = re.sub(r'<[^>]+>', '', s).strip()
                if text:
                    clean_snippets.append(text)

            if not clean_snippets:
                return f"[INFO] Market search completed for '{query}'. No high-impact alerts detected."

            return " | ".join(clean_snippets)
        except Exception as e:
            logger.warning(f"[WEB_SEARCH_WARN] Failed to fetch news: {e}")
            return f"[INFO] Normal market conditions. Unable to fetch online headlines ({e})."

    _forexfactory_cache = []
    _forexfactory_cache_time = 0.0
    _macro_cache = {}
    _macro_cache_time = {}

    @staticmethod
    def get_forexfactory_calendar(currency: str = "USD") -> list:
        """
        Directly fetches the economic calendar from ForexFactory's official JSON/API feed.
        Parses high-impact (Red Folder) events with 15-minute memory caching.
        """
        import time
        import json
        from datetime import datetime, timezone

        now = time.time()
        # Cache calendar for 15 minutes
        if WebTools._forexfactory_cache and (now - WebTools._forexfactory_cache_time < 900):
            return WebTools._forexfactory_cache

        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                events = json.loads(response.read().decode("utf-8"))

            WebTools._forexfactory_cache = events
            WebTools._forexfactory_cache_time = now
            logger.info(f"[FOREXFACTORY] Successfully loaded {len(events)} events from ForexFactory calendar.")
            return events
        except Exception as e:
            logger.warning(f"[FOREXFACTORY_WARN] Direct ForexFactory feed unreachable: {e}. Falling back to DuckDuckGo macro search.")
            return WebTools._forexfactory_cache

    @staticmethod
    def check_forexfactory_high_impact(symbol: str, buffer_minutes: int = 30) -> tuple:
        """
        Checks if a High-Impact (Red Folder) economic release on ForexFactory is imminent
        (within buffer_minutes before or after current time) matching the symbol's base/quote currency.
        """
        from datetime import datetime, timezone
        import dateutil.parser

        # Map common symbol currencies
        currencies_to_watch = ["USD"]
        if "EUR" in symbol:
            currencies_to_watch.append("EUR")
        if "JPY" in symbol:
            currencies_to_watch.append("JPY")
        if "GBP" in symbol:
            currencies_to_watch.append("GBP")

        events = WebTools.get_forexfactory_calendar()
        if not events:
            return False, ""

        now_utc = datetime.now(timezone.utc)

        for event in events:
            impact = event.get("impact", "")
            country = event.get("country", "")
            title = event.get("title", "")
            date_str = event.get("date", "")

            # Filter for High Impact red folder events matching symbol currency
            if impact.lower() == "high" and country in currencies_to_watch and date_str:
                try:
                    event_dt = dateutil.parser.isoparse(date_str)
                    diff_seconds = abs((now_utc - event_dt).total_seconds())
                    if diff_seconds <= (buffer_minutes * 60):
                        time_desc = "imminent" if now_utc <= event_dt else "recently released"
                        return True, f"ForexFactory High-Impact Event [{country} - {title}] is {time_desc} (Impact: HIGH)"
                except Exception:
                    continue

        return False, ""

    @staticmethod
    def get_forexfactory_daily_sentiment(symbol: str) -> str:
        """
        Extracts Today's Orange (Medium Impact) & Yellow (Low Impact) events from ForexFactory.
        Gives AI deep context on macroeconomic data flow without triggering a trade pause.
        """
        events = WebTools.get_forexfactory_calendar()
        if not events:
            return ""

        currencies_to_watch = ["USD"]
        if "EUR" in symbol:
            currencies_to_watch.append("EUR")
        if "JPY" in symbol:
            currencies_to_watch.append("JPY")
        if "GBP" in symbol:
            currencies_to_watch.append("GBP")

        summary_events = []
        for e in events:
            impact = e.get("impact", "").capitalize()
            country = e.get("country", "")
            title = e.get("title", "")
            if country in currencies_to_watch and impact in ["Medium", "Low", "High"]:
                actual = e.get("actual", "")
                forecast = e.get("forecast", "")
                prev = e.get("previous", "")
                data_stat = f" (Actual: {actual}, Forecast: {forecast})" if actual or forecast else ""
                summary_events.append(f"[{impact.upper()}] {country}: {title}{data_stat}")

        return " | ".join(summary_events[:6]) if summary_events else ""

    @staticmethod
    def get_upcoming_news_environment_assessment(symbol: str, df: Optional[any] = None) -> dict:
        """
        THE PREDICTIVE NEWS & PRE-EVENT RISK ASSESSOR:
        Combines scheduled unreleased economic releases WITH LIVE REAL-TIME PRICE ACTION (df).
        Analyzes whether the current live chart is:
        - Compressing into an explosive range before news (Low ATR / Squeeze)
        - Accumulating / Front-running in a directional drift
        - Hunting liquidity at equal highs/lows prior to the announcement
        """
        from datetime import datetime, timezone
        import dateutil.parser

        # 1. Live Chart Analysis (Current Price Action)
        chart_note = ""
        if df is not None and len(df) >= 10:
            latest_c = df['close'].iloc[-1]
            range_10 = df['high'].tail(10).max() - df['low'].tail(10).min()
            last_candle_body = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
            is_compressed = range_10 < (df['high'].tail(30).max() - df['low'].tail(30).min()) * 0.4
            if is_compressed:
                chart_note = f"Current Live Chart is heavily COMPRESSING (10-bar range: {range_10:.2f} pts). Energy is coiling for an explosive expansion."
            else:
                chart_note = f"Current Live Chart shows active price discovery around {latest_c:.2f} with a 10-bar volatility range of {range_10:.2f} pts."

        events = WebTools.get_forexfactory_calendar()
        if not events:
            return {
                "has_upcoming": False,
                "assessment": f"No scheduled releases found. {chart_note}"
            }

        currencies_to_watch = ["USD"]
        if "EUR" in symbol:
            currencies_to_watch.append("EUR")
        if "JPY" in symbol:
            currencies_to_watch.append("JPY")
        if "GBP" in symbol:
            currencies_to_watch.append("GBP")

        now_utc = datetime.now(timezone.utc)
        upcoming_events = []

        for e in events:
            country = e.get("country", "")
            date_str = e.get("date", "")
            impact = e.get("impact", "").capitalize()
            actual = e.get("actual", "")

            # Only look at future events or events within next 12 hours that have NO actual number yet
            if country in currencies_to_watch and date_str and not actual:
                try:
                    event_dt = dateutil.parser.isoparse(date_str)
                    diff_minutes = (event_dt - now_utc).total_seconds() / 60.0
                    # Focus on events occurring within the next 8 hours (0 to 480 mins)
                    if 0 < diff_minutes <= 480:
                        upcoming_events.append({
                            "title": e.get("title", ""),
                            "country": country,
                            "impact": impact,
                            "forecast": e.get("forecast", "N/A"),
                            "previous": e.get("previous", "N/A"),
                            "minutes_left": round(diff_minutes, 1)
                        })
                except Exception:
                    continue

        upcoming_events.sort(key=lambda x: x["minutes_left"])

        if not upcoming_events:
            return {
                "has_upcoming": False,
                "environment_mode": "OPEN_VOLATILITY",
                "summary": f"No high/medium impact news in next 8 hours. {chart_note}",
                "closest_event": None
            }

        closest = upcoming_events[0]
        mins = closest["minutes_left"]
        impact = closest["impact"].upper()

        if mins <= 60 and impact == "HIGH":
            mode = "PRE_RED_FOLDER_CAUTION"
            assessment = (
                f"ALERT: Red-Folder event [{closest['country']} - {closest['title']}] drops in {mins:.0f} mins! "
                f"Chart Correlation: {chart_note} "
                f"Expect drying liquidity, widening spreads, and high probability of sudden stop-hunts. "
                f"Forecast: {closest['forecast']} vs Previous: {closest['previous']}."
            )
        elif mins <= 120 and impact in ["HIGH", "MEDIUM"]:
            mode = "PRE_EVENT_POSITIONING"
            assessment = (
                f"Upcoming [{impact}] event [{closest['country']} - {closest['title']}] in {mins:.0f} mins. "
                f"Chart Correlation: {chart_note} "
                f"Forecast: {closest['forecast']} | Previous: {closest['previous']}."
            )
        else:
            mode = "NORMAL_SCHEDULED_AWARENESS"
            assessment = (
                f"Scheduled event [{closest['country']} - {closest['title']}] in {mins/60.0:.1f} hours ({mins:.0f} mins). "
                f"Chart Correlation: {chart_note} "
                f"Forecast: {closest['forecast']} vs Previous: {closest['previous']}."
            )

        return {
            "has_upcoming": True,
            "environment_mode": mode,
            "closest_event": closest,
            "assessment": assessment,
            "upcoming_queue": upcoming_events[:4]
        }

    @staticmethod
    def get_macroeconomic_brief(symbol: str = "GOLD", df: Optional[any] = None) -> str:
        """
        Global Macroeconomic Intelligence:
        Combines Predictive Pre-News Environment Assessment + ForexFactory Calendar + Web Market Sentiment.
        Correlates live real-time price action (df) with upcoming economic events.
        Caches results for 3 minutes to prevent network timeouts during rapid M1 candle evaluation.
        """
        import time
        now = time.time()
        if symbol in WebTools._macro_cache:
            if now - WebTools._macro_cache_time.get(symbol, 0) < 180:
                return WebTools._macro_cache[symbol]

        upcoming_assessment = WebTools.get_upcoming_news_environment_assessment(symbol, df=df)
        ff_context = WebTools.get_forexfactory_daily_sentiment(symbol)

        queries = [
            f"{symbol} price forecast DXY inflation fed rates",
            "US Dollar 10-year Treasury yield gold impact today"
        ]
        briefs = []
        if upcoming_assessment.get("has_upcoming"):
            briefs.append(f"[PREDICTIVE_NEWS_ASSESSOR] {upcoming_assessment['assessment']}")

        if ff_context:
            briefs.append(f"ForexFactory Calendar: {ff_context}")

        for q in queries:
            res = WebTools.search_news(q, max_results=1)
            if res and "[INFO]" not in res:
                briefs.append(res)

        if not briefs:
            result = "Macroeconomic Context: DXY and US Treasury Yields are in a balanced equilibrium. Gold spot trades primarily on technical flow."
        else:
            result = " | ".join(briefs)

        WebTools._macro_cache[symbol] = result
        WebTools._macro_cache_time[symbol] = now
        return result

    @staticmethod
    def detect_high_impact_news(news_text: str, symbol: str = "") -> tuple:
        """
        Analyzes ForexFactory calendar directly, plus news snippet string for red-folder high-impact keywords
        such as CPI, PPI, Retail Sales, Non-Farm, FOMC, Fed Rate, Powell, etc.
        """
        # 1. Direct ForexFactory Calendar Check
        if symbol:
            ff_active, ff_desc = WebTools.check_forexfactory_high_impact(symbol)
            if ff_active:
                return True, ff_desc

        # 2. Text keyword analysis fallback
        if not news_text or "[INFO]" in news_text:
            return False, ""

        keywords = [
            "CPI", "PPI", "RETAIL SALES", "NON-FARM", "NFP",
            "FOMC", "FED RATE", "INTEREST RATE DECISION",
            "POWELL", "INFLATION SURGE", "RATE HIKE", "RATE CUT",
            "BREAKING NEWS"
        ]
        upper_text = news_text.upper()
        found = [kw for kw in keywords if kw in upper_text]
        if found:
            return True, f"High-Impact Macro Event Detected: {', '.join(found)}"
        return False, ""


# =====================================================================
# 2. Math & Quant Calculator Tool
# =====================================================================
class MathTools:
    """Quantitative risk, lot sizing, and mathematical probability tools."""

    @staticmethod
    def calculate_lot_size(balance: float, risk_percent: float, sl_points: float, tick_value: float = 1.0) -> float:
        """
        Calculates exact lot size based on account balance and risk percentage.
        Formula: Lot = (Balance * (Risk / 100)) / (SL_Points * Tick_Value)
        """
        if sl_points <= 0 or balance <= 0:
            return 0.01

        risk_amount = balance * (risk_percent / 100.0)
        lot = risk_amount / (sl_points * tick_value)
        # Round to 2 decimal places, minimum 0.01 lot
        return max(0.01, round(lot, 2))

    @staticmethod
    def calculate_pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
        """Calculates standard floor pivot points for support and resistance."""
        pivot = (high + low + close) / 3.0
        r1 = (2.0 * pivot) - low
        s1 = (2.0 * pivot) - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2.0 * (pivot - low)
        s3 = low - 2.0 * (high - pivot)

        return {
            "pivot": round(pivot, 2),
            "r1": round(r1, 2),
            "r2": round(r2, 2),
            "r3": round(r3, 2),
            "s1": round(s1, 2),
            "s2": round(s2, 2),
            "s3": round(s3, 2),
        }

    @staticmethod
    def evaluate_kelly_criterion(win_rate: float, reward_ratio: float) -> float:
        """
        Calculates Kelly Criterion optimal risk fraction.
        K% = WinRate - ((1 - WinRate) / RewardRatio)
        """
        if reward_ratio <= 0:
            return 0.0
        kelly = win_rate - ((1.0 - win_rate) / reward_ratio)
        # Fractional Kelly (Half Kelly for safety in trading)
        safe_kelly = max(0.0, kelly * 0.5)
        return round(safe_kelly, 4)

# =====================================================================
# 3. Chart Crop & ASCII/Visual Representation Tool
# =====================================================================
class ChartTools:
    """Prepares structured candlestick matrix & ASCII chart for multimodal AI."""

    @staticmethod
    def render_ascii_chart(rates_df, width: int = 40, height: int = 10) -> str:
        """
        Renders a clean ASCII candlestick chart representation of recent price action.
        Provides spatial visual context for LLMs without requiring external GUI libs.
        """
        if rates_df is None or len(rates_df) < 10:
            return ""

        recent = rates_df.tail(width)
        highs = recent['high'].tolist()
        lows = recent['low'].tolist()
        closes = recent['close'].tolist()
        opens = recent['open'].tolist()

        max_p = max(highs)
        min_p = min(lows)
        price_range = max_p - min_p if max_p != min_p else 1.0

        chart_lines = []
        for h in range(height, -1, -1):
            level_p = min_p + (price_range * (h / height))
            line = f"{level_p:8.2f} | "
            for i in range(len(recent)):
                o = opens[i]
                c = closes[i]
                top = max(o, c)
                bot = min(o, c)
                
                # Check if price crosses this level
                if lows[i] <= level_p <= highs[i]:
                    if bot <= level_p <= top:
                        char = "#" if c >= o else "x"
                    else:
                        char = "|"
                else:
                    char = " "
                line += char
            chart_lines.append(line)

        chart_lines.append("         +" + "-" * len(recent))
        return "\n".join(chart_lines)

    @staticmethod
    def crop_chart_action_area(image_path: str, output_path: Optional[str] = None, focus_ratio: float = 0.65) -> Optional[str]:
        """
        Crops and zooms into the rightmost active trading area (the latest action candles and price scale).
        Cuts out redundant left-side history and top/bottom window chrome so Gemini Vision focuses
        100% on the latest order blocks, rejection wicks, and current price level.
        """
        if not image_path or not os.path.exists(image_path):
            return None

        try:
            from PIL import Image
            with Image.open(image_path) as img:
                w, h = img.size
                # Crop rightmost `focus_ratio` (e.g. last 65% of chart) and middle vertical trading zone
                left = int(w * (1.0 - focus_ratio))
                top = int(h * 0.05)       # trim top window header/tabs
                right = w
                bottom = int(h * 0.95)    # trim bottom taskbar/tabs

                cropped = img.crop((left, top, right, bottom))
                target = output_path or image_path.replace(".png", "_cropped.png")
                cropped.save(target, format="PNG", optimize=True)
                logger.info(f"[CHART_VISION_CROP] Cropped chart action zone saved to {target} ({cropped.size[0]}x{cropped.size[1]})")
                return target
        except Exception as e:
            logger.warning(f"[CHART_CROP_WARN] Failed to crop chart image: {e}")
            return image_path

# =====================================================================
# 4. Multi-Timeframe Confluence Scanner (M1, M5, M15, H1)
# =====================================================================
class MultiTimeframeScanner:
    """Fetches and aligns macro trends across M1, M5, M15, and H1 to prevent whipsaw."""

    @staticmethod
    def get_multi_tf_confluence(mt5_connector, symbol: str) -> Dict[str, Any]:
        """
        Scans M1, M5, M15, and H1 timeframes in parallel from local MT5.
        Returns trend direction, EMA alignment, and RSI for each timeframe.
        """
        from .analysis.indicators import calculate_ema, calculate_rsi, calculate_macd
        results = {}

        tfs = ["M1", "M5", "M15", "H1"]
        for tf in tfs:
            try:
                df = mt5_connector.get_rates(symbol, tf, count=35)
                if df is not None and len(df) >= 25:
                    ema9 = float(calculate_ema(df['close'], 9).iloc[-1])
                    ema21 = float(calculate_ema(df['close'], 21).iloc[-1])
                    rsi = float(calculate_rsi(df['close'], 14).iloc[-1])
                    macd_info = calculate_macd(df['close'])
                    cur = float(df['close'].iloc[-1])

                    bias = "BULLISH" if cur > ema9 > ema21 else ("BEARISH" if cur < ema9 < ema21 else "SIDEWAYS")
                    results[tf] = {
                        "trend": bias,
                        "close": round(cur, 2),
                        "ema_9": round(ema9, 2),
                        "ema_21": round(ema21, 2),
                        "rsi": round(rsi, 2),
                        "macd_momentum": macd_info.get("momentum", "NEUTRAL"),
                        "macd_hist": macd_info.get("histogram", 0.0)
                    }
                else:
                    results[tf] = {"trend": "UNKNOWN", "rsi": 50.0}
            except Exception as e:
                results[tf] = {"trend": "ERROR", "rsi": 50.0}

        # Calculate macro alignment score
        bullish_count = sum(1 for v in results.values() if v.get("trend") == "BULLISH")
        bearish_count = sum(1 for v in results.values() if v.get("trend") == "BEARISH")

        if bullish_count >= 3:
            macro_bias = "STRONG_BULLISH (Safe to BUY dips)"
        elif bearish_count >= 3:
            macro_bias = "STRONG_BEARISH (Safe to SHORT rallies)"
        else:
            macro_bias = "CONFLICTED / MIXED (High risk of whipsaw)"

        return {
            "macro_bias": macro_bias,
            "details": results
        }
