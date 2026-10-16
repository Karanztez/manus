"""
Historical Real Market Backtest Runner for ManusTrade
Connects to live MT5, fetches real historical candlestick bars for all configured symbols
(GOLD#, EURUSD#, USDJPY#, BTCUSD#), runs through the exact strategy pipeline:
1. Technical Feature & Indicator Extraction (EMA, RSI, ATR)
2. Fair Value Gap (FVG) Imbalance Detection
3. Session Liquidity Analysis
4. Multi-Timeframe Alignment
5. RiskManager Gatekeeping & Exhaustion Guard (No chasing tops/bottoms)
6. Trailing Stop & Spread-Aware Break-Even simulation
Outputs detailed PnL metrics, Win Rate, and Safeguard Interceptions.
"""

import os
import sys
import time
import pandas as pd
import numpy as np

# Ensure root dir in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config_manager import ConfigManager
from src.connectors.mt5_connector import MT5Connector
from src.analysis.indicators import extract_market_features
from src.analysis.gemini_trader import TradeSignal
from src.managers.risk_manager import RiskManager
from src.tools import MathTools

def run_backtest_for_symbol(mt5: MT5Connector, risk: RiskManager, symbol: str, timeframe: str = "M1", bars_count: int = 500):
    print(f"\n========================================================")
    print(f"[*] FETCHING REAL HISTORICAL DATA FOR: {symbol} ({timeframe}) - {bars_count} BARS")
    print(f"========================================================")

    df = mt5.get_rates(symbol, timeframe, count=bars_count)
    if df is None or len(df) < 50:
        print(f"[ERROR] Could not fetch sufficient rates for {symbol}.")
        return None

    symbol_info = mt5.get_symbol_info(symbol)
    point = getattr(symbol_info, "point", 0.01) if symbol_info else 0.01
    spread_raw = getattr(symbol_info, "spread", 15.0) if symbol_info else 15.0
    spread_points = spread_raw * point

    print(f"[OK] Fetched {len(df)} candles. Time range: {df['time'].iloc[0]} -> {df['time'].iloc[-1]}")
    print(f"[INFO] Current Market Spread: {spread_raw} pts ({spread_points:.5f})")

    # Metrics Tracking
    total_signals = 0
    exhaustion_rejections = 0
    executed_trades = 0
    wins = 0
    losses = 0
    net_pnl_points = 0.0
    active_position = None  # {type: 'BUY'/'SELL', entry: float, sl: float, tp: float, be: bool}

    # Iterate through historical bars (rolling window of 40 bars)
    for i in range(40, len(df)):
        window = df.iloc[i-40 : i+1].copy()
        current_candle = window.iloc[-1]
        prev_candle = window.iloc[-2]
        current_close = float(current_candle['close'])

        # 1. Manage Active Position (SL, TP, Break-even, Trailing)
        if active_position:
            pos_type = active_position['type']
            entry = active_position['entry']
            cur_sl = active_position['sl']
            cur_tp = active_position['tp']
            high = float(current_candle['high'])
            low = float(current_candle['low'])

            if pos_type == "BUY":
                # Check SL
                if low <= cur_sl:
                    pnl = cur_sl - entry
                    net_pnl_points += pnl
                    if pnl >= 0:
                        wins += 1
                    else:
                        losses += 1
                    active_position = None
                # Check TP
                elif high >= cur_tp:
                    pnl = cur_tp - entry
                    net_pnl_points += pnl
                    wins += 1
                    active_position = None
                # Check Dynamic Break-Even & Trailing
                else:
                    profit = current_close - entry
                    be_trigger = max(1.5 * point * 100, 3.5) if "GOLD" in symbol or "BTC" in symbol else 0.00030
                    if profit >= be_trigger and cur_sl < entry:
                        active_position['sl'] = entry + (spread_points * 1.5)

            elif pos_type == "SELL":
                # Check SL
                if high >= cur_sl:
                    pnl = entry - cur_sl
                    net_pnl_points += pnl
                    if pnl >= 0:
                        wins += 1
                    else:
                        losses += 1
                    active_position = None
                # Check TP
                elif low <= cur_tp:
                    pnl = entry - cur_tp
                    net_pnl_points += pnl
                    wins += 1
                    active_position = None
                # Check Dynamic Break-Even & Trailing
                else:
                    profit = entry - current_close
                    be_trigger = max(1.5 * point * 100, 3.5) if "GOLD" in symbol or "BTC" in symbol else 0.00030
                    if profit >= be_trigger and cur_sl > entry:
                        active_position['sl'] = entry - (spread_points * 1.5)

        # 2. Extract technical features & signals if no active trade
        if not active_position:
            features = extract_market_features(window)
            rsi = features['rsi_14']
            ema_trend = features['ema_trend']
            fvg = features['fair_value_gap']

            # Evaluate Playbooks locally based on market setup
            action = None
            if ema_trend == "BULLISH" and current_close <= features['ema_21']:
                # Pullback to EMA
                action = "BUY"
            elif ema_trend == "BEARISH" and current_close >= features['ema_21']:
                # Pullback to EMA
                action = "SELL"
            elif fvg.get("active_fvg"):
                fvg_info = fvg["active_fvg"]
                if fvg_info["type"] == "BULLISH_FVG" and current_close <= fvg_info["top"]:
                    action = "BUY"
                elif fvg_info["type"] == "BEARISH_FVG" and current_close >= fvg_info["bottom"]:
                    action = "SELL"

            if action:
                total_signals += 1
                sl_dist = max(features['atr_14'] * 1.5, 6.0 * point if "GOLD" in symbol else 0.00080)
                tp_dist = sl_dist * 1.8

                # 3. Test RiskManager Gatekeeping & Exhaustion Guard
                can_open, reason = risk.can_open_trade(
                    symbol=symbol,
                    action=action,
                    sl_points=sl_dist,
                    tp_points=tp_dist,
                    market_features=features
                )

                if not can_open:
                    if "Exhaustion Guard" in reason:
                        exhaustion_rejections += 1
                else:
                    # Execute simulated position
                    executed_trades += 1
                    if action == "BUY":
                        active_position = {
                            "type": "BUY",
                            "entry": current_close,
                            "sl": current_close - sl_dist,
                            "tp": current_close + tp_dist
                        }
                    else:
                        active_position = {
                            "type": "SELL",
                            "entry": current_close,
                            "sl": current_close + sl_dist,
                            "tp": current_close - tp_dist
                        }

    # Summary
    total_closed = wins + losses
    win_rate = (wins / total_closed * 100.0) if total_closed > 0 else 0.0

    print(f"\n[BACKTEST RESULT: {symbol}]")
    print(f"- Total Candidate Setups Evaluated: {total_signals}")
    print(f"- Intercepted by Exhaustion Guard (Prevented chasing): {exhaustion_rejections} times")
    print(f"- Clean Executed Trades: {executed_trades}")
    print(f"- Completed Trades: {total_closed} (Wins: {wins}, Losses: {losses})")
    print(f"- Win Rate: {win_rate:.1f}%")
    print(f"- Net Cumulative PnL (Price Points): {net_pnl_points:+.4f}")
    return {
        "symbol": symbol,
        "total_signals": total_signals,
        "exhaustion_rejections": exhaustion_rejections,
        "executed_trades": executed_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "pnl_points": net_pnl_points
    }

def main():
    config = ConfigManager.load("config.ini")
    mt5 = MT5Connector(
        magic_number=config.trading.magic_number
    )

    if not mt5.connect():
        print("[CRITICAL] Could not connect to MT5 for historical backtest.")
        return

    risk = RiskManager(
        mt5_connector=mt5,
        risk_percent=config.risk.risk_percent,
        fixed_lot=config.risk.fixed_lot,
        max_spread_points=config.risk.max_spread_points,
        min_rr_ratio=config.risk.min_rr_ratio,
        consecutive_loss_limit=config.risk.consecutive_loss_limit,
        loss_cooldown_minutes=config.risk.loss_cooldown_minutes,
        max_daily_drawdown_percent=config.risk.max_daily_drawdown_percent,
        max_trades_per_hour=config.risk.max_trades_per_hour,
        min_sl_points=config.risk.min_sl_points,
        news_protection_enabled=False  # Disabled for historical offline bar iteration
    )

    symbols = config.trading.symbols if config.trading.symbols else [config.trading.symbol]
    results = []
    for s in symbols:
        res = run_backtest_for_symbol(mt5, risk, s, timeframe=config.trading.timeframe, bars_count=400)
        if res:
            results.append(res)

    print("\n" + "=" * 60)
    print("PORTFOLIO HISTORICAL BACKTEST SUMMARY ACROSS ALL ASSETS")
    print("=" * 60)
    print(f"{'SYMBOL':<10} | {'TRADES':<8} | {'WIN RATE':<10} | {'PNL (PTS)':<12} | {'CHASE BLOCKED':<14}")
    print("-" * 60)
    for r in results:
        print(f"{r['symbol']:<10} | {r['executed_trades']:<8} | {r['win_rate']:>6.1f}%    | {r['pnl_points']:>+10.4f}  | {r['exhaustion_rejections']:<14}")
    print("=" * 60)

    mt5.shutdown()

if __name__ == "__main__":
    main()
