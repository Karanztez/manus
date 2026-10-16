"""
Indicators & Market Feature Extraction
Pre-calculates technical indicators so Gemini can make precise decisions
with lower token usage.
"""

import pandas as pd
import numpy as np

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    
    # Smooth with EMA-like Wilder smoothing
    for i in range(period, len(series)):
        avg_gain.iloc[i] = (avg_gain.iloc[i-1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i-1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df['high']
    low = df['low']
    close_prev = df['close'].shift(1)
    
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def calculate_bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0) -> dict:
    """Calculates Bollinger Bands for mean-reversion and volatility squeeze."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    bandwidth = (upper - lower) / sma * 100.0
    return {
        "bb_upper": round(float(upper.iloc[-1]), 2) if not pd.isna(upper.iloc[-1]) else 0.0,
        "bb_middle": round(float(sma.iloc[-1]), 2) if not pd.isna(sma.iloc[-1]) else 0.0,
        "bb_lower": round(float(lower.iloc[-1]), 2) if not pd.isna(lower.iloc[-1]) else 0.0,
        "bb_bandwidth": round(float(bandwidth.iloc[-1]), 2) if not pd.isna(bandwidth.iloc[-1]) else 0.0
    }

def detect_order_blocks(df: pd.DataFrame) -> dict:
    """
    SMC Order Block (OB) Detection:
    Bullish Order Block: The last bearish candle before a strong bullish impulse break.
    Bearish Order Block: The last bullish candle before a strong bearish impulse break.
    """
    if len(df) < 10:
        return {"active_ob": None}

    bullish_ob = None
    bearish_ob = None

    for i in range(len(df) - 15, len(df) - 2):
        if i < 2:
            continue
        c_prev = df.iloc[i]
        c_next = df.iloc[i + 1]
        c_after = df.iloc[i + 2]

        # Strong Bullish Impulse breaking previous high
        if c_prev['close'] < c_prev['open'] and c_next['close'] > c_next['open']:
            if (c_after['close'] > c_prev['high']) and ((c_next['close'] - c_next['open']) > (c_prev['open'] - c_prev['close']) * 1.5):
                bullish_ob = {
                    "type": "BULLISH_ORDER_BLOCK",
                    "high": round(float(c_prev['high']), 2),
                    "low": round(float(c_prev['low']), 2),
                    "mitigated": False
                }
        # Strong Bearish Impulse breaking previous low
        elif c_prev['close'] > c_prev['open'] and c_next['close'] < c_next['open']:
            if (c_after['close'] < c_prev['low']) and ((c_next['open'] - c_next['close']) > (c_prev['close'] - c_prev['open']) * 1.5):
                bearish_ob = {
                    "type": "BEARISH_ORDER_BLOCK",
                    "high": round(float(c_prev['high']), 2),
                    "low": round(float(c_prev['low']), 2),
                    "mitigated": False
                }

    active = bullish_ob if bullish_ob else bearish_ob
    return {"active_ob": active}

def detect_fair_value_gaps(df: pd.DataFrame) -> dict:
    """
    Detects active Fair Value Gaps (FVG) / Imbalances in recent candles.
    Bullish FVG: Candle[i-2].high < Candle[i].low (Unfilled bullish imbalance)
    Bearish FVG: Candle[i-2].low > Candle[i].high (Unfilled bearish imbalance)
    """
    if len(df) < 5:
        return {"has_fvg": False, "status": "Insufficient data"}

    bullish_fvgs = []
    bearish_fvgs = []

    # Scan last 15 candles for imbalances
    for i in range(len(df) - 15, len(df) - 1):
        if i < 2:
            continue
        c1 = df.iloc[i - 2]
        c3 = df.iloc[i]

        # Bullish Gap
        if c3['low'] > c1['high']:
            gap_size = round(float(c3['low'] - c1['high']), 2)
            if gap_size > 0.5:  # meaningful gap
                bullish_fvgs.append({
                    "type": "BULLISH_FVG",
                    "top": round(float(c3['low']), 2),
                    "bottom": round(float(c1['high']), 2),
                    "gap_size": gap_size
                })
        # Bearish Gap
        elif c1['low'] > c3['high']:
            gap_size = round(float(c1['low'] - c3['high']), 2)
            if gap_size > 0.5:
                bearish_fvgs.append({
                    "type": "BEARISH_FVG",
                    "top": round(float(c1['low']), 2),
                    "bottom": round(float(c3['high']), 2),
                    "gap_size": gap_size
                })

    latest_fvg = None
    if bullish_fvgs:
        latest_fvg = bullish_fvgs[-1]
    elif bearish_fvgs:
        latest_fvg = bearish_fvgs[-1]

    return {
        "active_fvg": latest_fvg,
        "recent_bullish_fvgs_count": len(bullish_fvgs),
        "recent_bearish_fvgs_count": len(bearish_fvgs)
    }

def get_market_session() -> dict:
    """
    Determines current Forex/Gold trading session and volatility expectations (UTC-based).
    Asian: 00:00 - 08:00 UTC (Low-Medium Volatility, Range-bound)
    London: 08:00 - 13:00 UTC (High Volatility, Real Breakouts)
    US-London Overlap: 13:00 - 16:30 UTC (Peak Liquidity & High Momentum)
    Late US: 16:30 - 21:00 UTC (Moderate, Profit Taking)
    Twilight/Dead Zone: 21:00 - 23:59 UTC (Low Liquidity, False Breakouts)
    """
    import datetime
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    hour = now_utc.hour + (now_utc.minute / 60.0)

    if 13.0 <= hour < 16.5:
        session_name = "US_LONDON_OVERLAP"
        liquidity = "PEAK"
        guidance = "Highest liquidity & momentum. Ideal for trend continuation and high-conviction scalps."
    elif 8.0 <= hour < 13.0:
        session_name = "LONDON_SESSION"
        liquidity = "HIGH"
        guidance = "Clean trend expansions and genuine breakouts. Strong volume support."
    elif 16.5 <= hour < 21.0:
        session_name = "LATE_US_SESSION"
        liquidity = "MODERATE"
        guidance = "Moderate volume. Be cautious of profit taking and trend exhaustion."
    elif 0.0 <= hour < 8.0:
        session_name = "ASIAN_SESSION"
        liquidity = "LOW_TO_MODERATE"
        guidance = "Range-bound / Accumulation phase. Trade support/resistance bounces or HOLD."
    else:
        session_name = "DEAD_ZONE_TWILIGHT"
        liquidity = "VERY_LOW"
        guidance = "Low liquidity, wide spreads, and erratic noise. High risk of fakeouts. Prefer HOLD."

    return {
        "session": session_name,
        "liquidity_level": liquidity,
        "trading_guidance": guidance,
        "utc_time": now_utc.strftime("%H:%M UTC")
    }

def extract_market_features(df: pd.DataFrame) -> dict:
    """
    Computes technical indicators and returns a compact structured summary
    ready to be sent in the prompt to Gemini.
    """
    df = df.copy()
    df['ema_9'] = calculate_ema(df['close'], 9)
    df['ema_21'] = calculate_ema(df['close'], 21)
    df['ema_50'] = calculate_ema(df['close'], 50)
    df['rsi_14'] = calculate_rsi(df['close'], 14)
    df['atr_14'] = calculate_atr(df, 14)

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    recent_candles = []
    for _, row in df.iloc[-6:-1].iterrows():
        candle_type = "BULLISH" if row['close'] >= row['open'] else "BEARISH"
        recent_candles.append({
            "time": str(row['time']),
            "open": round(float(row['open']), 2),
            "high": round(float(row['high']), 2),
            "low": round(float(row['low']), 2),
            "close": round(float(row['close']), 2),
            "type": candle_type
        })

    fvg_data = detect_fair_value_gaps(df)
    ob_data = detect_order_blocks(df)
    bb_data = calculate_bollinger_bands(df['close'], period=20)
    session_data = get_market_session()

    # Liquidity Pool Highs & Lows (Equal Highs / Equal Lows)
    rolling_20_high = round(float(df['high'].tail(20).max()), 2)
    rolling_20_low = round(float(df['low'].tail(20).min()), 2)
    liquidity_pools = {
        "buy_side_liquidity_bsl": rolling_20_high,
        "sell_side_liquidity_ssl": rolling_20_low,
        "current_distance_to_bsl": round(float(rolling_20_high - latest['close']), 2),
        "current_distance_to_ssl": round(float(latest['close'] - rolling_20_low), 2)
    }

    features = {
        "current_price": float(latest['close']),
        "prev_close": float(prev['close']),
        "ema_9": round(float(latest['ema_9']), 2),
        "ema_21": round(float(latest['ema_21']), 2),
        "ema_50": round(float(latest['ema_50']), 2),
        "rsi_14": round(float(latest['rsi_14']), 2),
        "atr_14": round(float(latest['atr_14']), 2),
        "bollinger_bands": bb_data,
        "ema_trend": "BULLISH" if latest['ema_9'] > latest['ema_21'] > latest['ema_50'] else (
            "BEARISH" if latest['ema_9'] < latest['ema_21'] < latest['ema_50'] else "SIDEWAYS"
        ),
        "market_session": session_data,
        "fair_value_gap": fvg_data,
        "order_block": ob_data,
        "liquidity_pools": liquidity_pools,
        "recent_candles": recent_candles,
        "support_level": rolling_20_low,
        "resistance_level": rolling_20_high,
    }

    return features
