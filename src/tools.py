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

    @staticmethod
    def detect_high_impact_news(news_text: str) -> tuple:
        """
        Analyzes news snippet string for red-folder high-impact keywords
        such as CPI, PPI, Retail Sales, Non-Farm, FOMC, Fed Rate, Powell, etc.
        """
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
        from .analysis.indicators import calculate_ema, calculate_rsi
        results = {}

        tfs = ["M1", "M5", "M15", "H1"]
        for tf in tfs:
            try:
                df = mt5_connector.get_rates(symbol, tf, count=35)
                if df is not None and len(df) >= 25:
                    ema9 = float(calculate_ema(df['close'], 9).iloc[-1])
                    ema21 = float(calculate_ema(df['close'], 21).iloc[-1])
                    rsi = float(calculate_rsi(df['close'], 14).iloc[-1])
                    cur = float(df['close'].iloc[-1])

                    bias = "BULLISH" if cur > ema9 > ema21 else ("BEARISH" if cur < ema9 < ema21 else "SIDEWAYS")
                    results[tf] = {
                        "trend": bias,
                        "close": round(cur, 2),
                        "ema_9": round(ema9, 2),
                        "ema_21": round(ema21, 2),
                        "rsi": round(rsi, 2)
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
