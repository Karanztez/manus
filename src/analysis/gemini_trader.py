"""
Gemini Trader Module
Supports multi-key pool with automatic failover / key rotation when hitting quota or rate limits.
Uses the official google-genai SDK to analyze market structures and return
validated JSON decisions with Pydantic structured output.
"""

import json
import logging
from typing import Literal, Optional, List
from dataclasses import dataclass, field
from google import genai
from google.genai import types

logger = logging.getLogger("ManusTrade.Gemini")

try:
    from pydantic import BaseModel, Field
    HAS_PYDANTIC = True
    class TradeSignal(BaseModel):
        action: Literal["BUY", "SELL", "HOLD", "CLOSE"] = Field(
            description="Trade action decision based on market structure and technical analysis"
        )
        confidence: float = Field(
            description="Confidence score from 0.0 to 1.0 (e.g. 0.85 = high confidence)"
        )
        sl_points: float = Field(
            default=0.0,
            description="Suggested Stop Loss distance in points/price units based on ATR or support/resistance"
        )
        tp_points: float = Field(
            default=0.0,
            description="Suggested Take Profit distance in points/price units (at least 1.5x of SL)"
        )
        risk_reward_ratio: float = Field(
            default=0.0,
            description="Target Risk to Reward ratio (e.g. 1.5 or 2.0)"
        )
        reasoning: str = Field(
            description="Detailed technical reasoning (EMA alignment, RSI divergence, candlestick rejection, market structure)"
        )
except Exception:
    HAS_PYDANTIC = False
    @dataclass
    class TradeSignal:
        action: str = "HOLD"
        confidence: float = 0.0
        sl_points: float = 0.0
        tp_points: float = 0.0
        risk_reward_ratio: float = 0.0
        reasoning: str = "Pydantic fallback"

        def model_dump_json(self):
            return json.dumps(self.__dict__)

class GeminiTrader:
    def __init__(self, api_keys: List[str], model_name: str = "gemini-3.8-flash"):
        self.api_keys = [k for k in api_keys if k and k != "YOUR_GEMINI_API_KEY"]
        self.current_key_index = 0
        self.model_name = model_name
        self._init_client()

    def _init_client(self):
        if not self.api_keys:
            self.client = None
            return
        current_key = self.api_keys[self.current_key_index]
        masked = current_key[:6] + "..." + current_key[-4:]
        logger.info(f"[KEY_INIT] Using Gemini API Key index {self.current_key_index + 1}/{len(self.api_keys)} ({masked})")
        self.client = genai.Client(api_key=current_key)

    def _rotate_key(self) -> bool:
        """Rotates to the next available API key in the pool."""
        if len(self.api_keys) <= 1:
            logger.warning("[KEY_ROTATION] No alternative keys available in pool.")
            return False

        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        new_key = self.api_keys[self.current_key_index]
        masked = new_key[:6] + "..." + new_key[-4:]
        logger.info(f"[KEY_ROTATED] Switched to Key index {self.current_key_index + 1}/{len(self.api_keys)} ({masked})")
        self._init_client()
        return True

    def analyze(self, symbol: str, timeframe: str, market_data: dict, current_position: Optional[str] = None, chart_visual: str = "", web_context: str = "") -> Optional[TradeSignal]:
        """
        Sends structured market technical summary to Gemini and extracts
        strictly-typed trade signal using google-genai structured output.
        Automatically switches to next API key if quota limit or error occurs.
        """
        if not self.api_keys:
            logger.error("[ERROR] No valid Gemini API keys configured.")
            return None

        system_instruction = (
            "You are an elite, highly disciplined Forex and Commodities Algorithmic Trader with tools. "
            "You have access to live Market News, Quant Pivot Points, Technical Indicators, and Spatial Price Action. "
            "Your objective is capital preservation first, then high-probability trend/momentum setups. "
            "You strictly adhere to risk-to-reward ratios (minimum 1:1.5). "
            "When the market is choppy, ambiguous, or in sideways consolidation, prefer 'HOLD'. "
            "If an existing position is moving against the structure, suggest 'CLOSE'."
        )

        prompt = f"""
Analyze the current market condition and provide trading decision for:
- Asset: {symbol}
- Timeframe: {timeframe}
- Current Active Position: {current_position if current_position else 'None'}

=== 1. FINANCIAL NEWS & MACRO SENTIMENT (Web Tool) ===
{web_context if web_context else 'Normal market conditions.'}

=== 2. PRICE ACTION MATRIX & RECENT STRUCTURE (Spatial Crop) ===
{chart_visual if chart_visual else 'Matrix not available'}

=== 3. MARKET TECHNICAL & QUANT DATA ===
{json.dumps(market_data, indent=2)}

Guidelines:
1. BUY only when EMA indicates Bullish Trend or Pullback to Support with RSI not overbought (>70).
2. SELL only when EMA indicates Bearish Trend or Rally to Resistance with RSI not oversold (<30).
3. If current trend is weak, mixed, or no clear edge, choose 'HOLD'.
4. Calculate sl_points realistically using ATR (1.5x - 2.0x ATR) or recent swing high/low.
5. Set tp_points such that tp_points / sl_points >= 1.5 (Risk to Reward >= 1.5).
"""

        max_attempts = len(self.api_keys)
        for attempt in range(max_attempts):
            try:
                gen_config = {
                    "system_instruction": system_instruction,
                    "response_mime_type": "application/json",
                    "temperature": 0.2,
                }
                if HAS_PYDANTIC:
                    gen_config["response_schema"] = TradeSignal

                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(**gen_config),
                )
                
                if HAS_PYDANTIC:
                    signal = TradeSignal.model_validate_json(response.text)
                else:
                    data = json.loads(response.text)
                    signal = TradeSignal(**data)
                logger.info(f"[ANALYSIS] {symbol} {timeframe} | Decision: {signal.action} (Confidence: {signal.confidence:.2f}) | {signal.reasoning}")
                return signal
            except Exception as e:
                err_msg = str(e)
                logger.warning(f"[API_WARN] Key index {self.current_key_index + 1} encountered error: {err_msg}")
                # Check for rate limit, quota exhaustion or permission error
                if any(err in err_msg.lower() for err in ["429", "quota", "resource_exhausted", "limit", "invalid"]):
                    logger.warning("[QUOTA_EXHAUSTED] Rate limit or quota reached. Triggering automatic key rotation...")
                    if not self._rotate_key():
                        break
                else:
                    # Generic error fallback rotation
                    if not self._rotate_key():
                        break

        logger.error("[ERROR] All Gemini API keys exhausted or failed.")
        return None
