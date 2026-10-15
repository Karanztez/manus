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

    features = {
        "current_price": float(latest['close']),
        "prev_close": float(prev['close']),
        "ema_9": round(float(latest['ema_9']), 2),
        "ema_21": round(float(latest['ema_21']), 2),
        "ema_50": round(float(latest['ema_50']), 2),
        "rsi_14": round(float(latest['rsi_14']), 2),
        "atr_14": round(float(latest['atr_14']), 2),
        "ema_trend": "BULLISH" if latest['ema_9'] > latest['ema_21'] > latest['ema_50'] else (
            "BEARISH" if latest['ema_9'] < latest['ema_21'] < latest['ema_50'] else "SIDEWAYS"
        ),
        "recent_candles": recent_candles,
        "support_level": round(float(df['low'].tail(20).min()), 2),
        "resistance_level": round(float(df['high'].tail(20).max()), 2),
    }

    return features
