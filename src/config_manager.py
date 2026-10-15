"""
Configuration Management
Supports single or multiple Gemini API keys with automatic round-robin / fallback.
"""

import os
import configparser
from typing import List
from dataclasses import dataclass

@dataclass
class GeminiConfig:
    api_keys: List[str]
    model_name: str

@dataclass
class TradingConfig:
    symbol: str
    timeframe: str
    history_bars: int
    min_confidence: float
    magic_number: int

@dataclass
class RiskConfig:
    risk_percent: float
    fixed_lot: float
    max_spread_points: float
    min_rr_ratio: float

@dataclass
class MT5Config:
    login: int
    password: str
    server: str

@dataclass
class AppConfig:
    gemini: GeminiConfig
    trading: TradingConfig
    risk: RiskConfig
    mt5: MT5Config

class ConfigManager:
    @staticmethod
    def load(config_path: str = "config.ini") -> AppConfig:
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")

        parser = configparser.ConfigParser()
        parser.read(config_path, encoding="utf-8-sig")

        # Parse keys (comma-separated or fallback)
        raw_keys = parser.get("gemini", "api_keys", fallback="")
        if not raw_keys:
            raw_keys = parser.get("gemini", "api_key", fallback="")
        
        if not raw_keys:
            raw_keys = os.getenv("GEMINI_API_KEY", "")

        api_keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

        gemini_cfg = GeminiConfig(
            api_keys=api_keys,
            model_name=parser.get("gemini", "model_name", fallback="gemini-3.8-flash")
        )

        trading_cfg = TradingConfig(
            symbol=parser.get("trading", "symbol", fallback="XAUUSD"),
            timeframe=parser.get("trading", "timeframe", fallback="M15"),
            history_bars=parser.getint("trading", "history_bars", fallback=40),
            min_confidence=parser.getfloat("trading", "min_confidence", fallback=0.75),
            magic_number=parser.getint("trading", "magic_number", fallback=888999)
        )

        risk_cfg = RiskConfig(
            risk_percent=parser.getfloat("risk", "risk_percent", fallback=1.0),
            fixed_lot=parser.getfloat("risk", "fixed_lot", fallback=0.01),
            max_spread_points=parser.getfloat("risk", "max_spread_points", fallback=50.0),
            min_rr_ratio=parser.getfloat("risk", "min_rr_ratio", fallback=1.5)
        )

        mt5_cfg = MT5Config(
            login=parser.getint("mt5", "login", fallback=0),
            password=parser.get("mt5", "password", fallback=""),
            server=parser.get("mt5", "server", fallback="XMGlobal-MT5 5")
        )

        return AppConfig(gemini=gemini_cfg, trading=trading_cfg, risk=risk_cfg, mt5=mt5_cfg)
