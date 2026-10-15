"""
Gemini Trader Module
Supports multi-key pool with automatic failover / key rotation when hitting quota or rate limits.
Uses the official google-genai SDK to analyze market structures and return
validated JSON decisions with Pydantic structured output.
"""

import os
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
        self.memory: List[str] = []  # Rolling contextual working memory (last 5 decisions/scans)
        self._init_client()

    def record_memory(self, entry: str):
        """Maintains rolling fast memory buffer of recent market structure events."""
        self.memory.append(entry)
        if len(self.memory) > 5:
            self.memory.pop(0)

    def get_memory_context(self) -> str:
        """Returns condensed sequential context for the AI."""
        if not self.memory:
            return "No previous decisions recorded yet (Initial cycle)."
        return "\n".join(f"- {m}" for m in self.memory)

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

    def analyze(self, symbol: str, timeframe: str, market_data: dict, current_position: Optional[str] = None, chart_visual: str = "", web_context: str = "", local_scan_note: str = "", image_path: Optional[str] = None) -> Optional[TradeSignal]:
        """
        Sends structured market technical summary + Fast Memory + Real Screenshot Image to Gemini Vision.
        Extracts strictly-typed trade signal using google-genai structured output.
        Automatically switches to next API key if quota limit or error occurs.
        """
        if not self.api_keys:
            logger.error("[ERROR] No valid Gemini API keys configured.")
            return None

        system_instruction = (
            "You are an elite, highly disciplined Forex and Commodities Algorithmic Trader with Computer Vision capability. "
            "You inspect live MT5 candlestick chart screenshots to identify exact patterns (Doji, Shooting Star, Hammer, Engulfing), "
            "candlestick rejection wicks, trendlines, and key Support/Resistance liquidity zones. "
            "You strictly adhere to risk-to-reward ratios (minimum 1:1.5). "
            "When the market is choppy, ambiguous, or in sideways consolidation, prefer 'HOLD'. "
            "If an existing position is moving against the structure, suggest 'CLOSE'."
        )

        memory_context = self.get_memory_context()

        prompt = f"""
Analyze the current market condition and provide trading decision for:
- Asset: {symbol}
- Timeframe: {timeframe}
- Current Active Position: {current_position if current_position else 'None'}
- Local Scanner Trigger Note: {local_scan_note if local_scan_note else 'Regular Candle Scan'}

=== 1. AI SHORT-TERM WORKING MEMORY (Previous Steps & Decisions) ===
{memory_context}

=== 2. FINANCIAL NEWS & MACRO SENTIMENT (Web Tool) ===
{web_context if web_context else 'Normal market conditions.'}

=== 3. PRICE ACTION MATRIX & RECENT STRUCTURE (Spatial Crop) ===
{chart_visual if chart_visual else 'Matrix not available'}

=== 4. MARKET TECHNICAL & QUANT DATA ===
{json.dumps(market_data, indent=2)}

Guidelines:
1. Multi-Timeframe Confluence Rule (CRITICAL):
   - Check 'multi_timeframe_alignment' in technical data (M1, M5, M15, H1).
   - If macro bias is CONFLICTED / MIXED, be extremely conservative and prefer 'HOLD'.
   - NEVER BUY if M15 and H1 are strongly BEARISH, and NEVER SELL if M15 and H1 are strongly BULLISH (unless there is a massive reversal rejection wick at key Pivot levels).
2. BUY Symmetrical Edge:
   - Trend continuation: Higher timeframes (M5/M15) are Bullish + M1 pullback to Support/EMA.
   - Reversal bounce: Sharp rejection wick at major Support/S1 or Oversold RSI (<35) rebounding up.
3. SELL Symmetrical Edge (Short Selling / Mean-Reversion):
   - Trend continuation: Higher timeframes (M5/M15) are Bearish + M1 rally into Resistance/EMA.
   - Reversal top / Fakeout: Sharp rejection wick at Resistance/R1 (e.g. Shooting Star / Bearish Engulfing after a strong rally) or Overbought RSI (>65) breaking below EMA 9.
4. If market is completely flat and compressed with zero momentum, choose 'HOLD'.
4. Calculate sl_points realistically using ATR (1.2x - 1.8x ATR) or recent swing high/low.
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

                contents_payload = [prompt]
                if image_path and os.path.exists(image_path):
                    try:
                        with open(image_path, "rb") as f:
                            img_bytes = f.read()
                        contents_payload.append(types.Part.from_bytes(data=img_bytes, mime_type="image/png"))
                        logger.info(f"[VISION_DISPATCH] Embedded real chart screenshot ({len(img_bytes)} bytes) into Gemini payload.")
                    except Exception as e:
                        logger.warning(f"[VISION_WARN] Failed to read chart image {image_path}: {e}")

                models_to_try = [self.model_name, "gemini-2.5-flash", "gemini-1.5-flash"]
                last_exc = None
                response = None
                for m in models_to_try:
                    try:
                        response = self.client.models.generate_content(
                            model=m,
                            contents=contents_payload,
                            config=types.GenerateContentConfig(**gen_config),
                        )
                        break
                    except Exception as err:
                        last_exc = err
                        if "503" in str(err) or "UNAVAILABLE" in str(err):
                            continue
                        raise err

                if response is None:
                    if last_exc:
                        raise last_exc
                    raise RuntimeError("No response from Gemini API models.")
                
                if HAS_PYDANTIC:
                    signal = TradeSignal.model_validate_json(response.text)
                else:
                    data = json.loads(response.text)
                    signal = TradeSignal(**data)
                
                # Record to working memory for sequential continuity
                mem_entry = f"[{timeframe}] Action: {signal.action} (Conf: {signal.confidence:.2f}) | {signal.reasoning[:120]}..."
                self.record_memory(mem_entry)

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
