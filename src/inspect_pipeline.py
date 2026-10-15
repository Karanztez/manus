"""
ManusTrade Live Inspector CLI
Displays the real step-by-step pipeline in terminal:
[STEP 1] Fetch Real MT5 Market Data & Account
[STEP 2] Web News Search (DuckDuckGo Live Scrape)
[STEP 3] Math & Quant Pivot Calculation
[STEP 4] Candlestick Spatial Matrix Rendering
[STEP 5] Gemini AI Live Inference & Reasoning
"""

import sys
import os
import json
import time
import socket

# Ensure root in path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from src.config_manager import ConfigManager
from src.connectors.mt5_connector import MT5Connector
from src.analysis.indicators import extract_market_features
from src.analysis.gemini_trader import GeminiTrader
from src.tools import WebTools, MathTools, ChartTools

def print_banner():
    print("\n" + "=" * 65)
    print("      MANUSTRADE DEEP PIPELINE INSPECTOR (LIVE DIAGNOSTIC)")
    print("=" * 65)

def run_inspector():
    print_banner()

    # Load config
    cfg_path = os.path.join(BASE_DIR, "config.ini")
    config = ConfigManager.load(cfg_path)
    symbol = config.trading.symbol
    timeframe = config.trading.timeframe

    print(f"\n[CONFIG] Target Asset: {symbol} | Timeframe: {timeframe} | Model: {config.gemini.model_name}")

    # STEP 1: Connect to Live Gateway or Direct MT5
    print("\n>>> [STEP 1/5] FETCHING LIVE MARKET & CANDLE DATA FROM GATEWAY...")
    rates_data = None
    acc_data = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        s.connect(("127.0.0.1", 9999))
        s.sendall(b'{"action":"GET_STATUS"}\n')
        resp_raw = s.recv(65536).decode("utf-8")
        s.close()
        for line in resp_raw.splitlines():
            msg = json.loads(line)
            if msg.get("type") == "STATUS_UPDATE":
                d = msg.get("data", {})
                acc_data = d.get("account")
                rates_data = d.get("market", {}).get("candles")
                break
    except Exception as e:
        print(f"    [GATEWAY_IPC_OFFLINE] Connecting directly to MT5: {e}")

    if acc_data:
        print(f"    [ACCOUNT] Login: {acc_data.get('login')} | Server: {acc_data.get('server')} | Balance: {acc_data.get('balance'):,.2f} {acc_data.get('currency')}")

    import pandas as pd
    if rates_data:
        df = pd.DataFrame(rates_data)
        df['time'] = pd.to_datetime(df['time'], unit='s')
    else:
        mt5 = MT5Connector(magic_number=config.trading.magic_number)
        mt5.connect()
        df = mt5.get_rates(symbol, timeframe, count=40)

    if df is None or len(df) == 0:
        print(f"[FAIL] Unable to fetch rates for {symbol}")
        return

    current_candle = df.iloc[-1]
    print(f"    [MARKET] Last Candle: {current_candle['time']} | Close: {current_candle['close']} | High: {current_candle['high']} | Low: {current_candle['low']}")

    # STEP 2: Web Search
    print("\n>>> [STEP 2/5] LIVE WEB NEWS SEARCH & MACRO SENTIMENT (DuckDuckGo)...")
    t0 = time.time()
    news = WebTools.search_news(f"{symbol} gold price live market news", max_results=2)
    t_web = time.time() - t0
    print(f"    [WEB_RESULT] Fetched in {t_web:.2f}s:")
    print(f"    \"{news[:200]}...\"")

    # STEP 3: Math & Quant Calculation
    print("\n>>> [STEP 3/5] QUANT & MATHEMATICAL PIVOT POINT ANALYSIS...")
    last_completed = df.iloc[-2]
    pivots = MathTools.calculate_pivot_points(float(last_completed['high']), float(last_completed['low']), float(last_completed['close']))
    bal = acc_data.get('balance', 1000.0) if acc_data else 1000.0
    lot_preview = MathTools.calculate_lot_size(balance=bal, risk_percent=config.risk.risk_percent, sl_points=80.0)
    print(f"    [PIVOT_MATH] High: {last_completed['high']} | Low: {last_completed['low']} | Close: {last_completed['close']}")
    print(f"    [LEVELS] Pivot: {pivots['pivot']} | Resistance 1: {pivots['r1']} | Support 1: {pivots['s1']}")
    print(f"    [QUANT_LOT] Dynamic Sizing for 80pt SL: {lot_preview} Lots")

    # STEP 4: Spatial Matrix Render
    print("\n>>> [STEP 4/5] RENDERING SPATIAL CANDLESTICK MATRIX (Visual Crop for AI)...")
    chart_matrix = ChartTools.render_ascii_chart(df, width=30, height=7)
    print(chart_matrix)

    # STEP 5: Gemini AI Analysis
    print("\n>>> [STEP 5/5] DISPATCHING FULL MULTI-MODAL PROMPT TO GEMINI AI...")
    features = extract_market_features(df)
    features['pivot_points'] = pivots

    ai = GeminiTrader(api_keys=config.gemini.api_keys, model_name=config.gemini.model_name)
    t0 = time.time()
    signal = ai.analyze(
        symbol=symbol,
        timeframe=timeframe,
        market_data=features,
        current_position=None,
        chart_visual=chart_matrix,
        web_context=news
    )
    t_ai = time.time() - t0

    print(f"    [AI_RESPONSE] Generated in {t_ai:.2f}s:")
    if signal:
        print("    " + "-" * 55)
        print(f"    DECISION ACTION   : {signal.action}")
        print(f"    CONFIDENCE SCORE  : {signal.confidence * 100:.1f}%")
        print(f"    STOP LOSS (SL)    : {signal.sl_points} points")
        print(f"    TAKE PROFIT (TP)  : {signal.tp_points} points")
        print(f"    RISK / REWARD     : {signal.risk_reward_ratio}")
        print(f"    REASONING         : {signal.reasoning}")
        print("    " + "-" * 55)
    else:
        print("    [FAIL] No signal received from AI.")

    print("\n[OK] Pipeline diagnostic inspection completed successfully.\n")

if __name__ == "__main__":
    run_inspector()
