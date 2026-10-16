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
    def __init__(self, api_keys: List[str], model_name: str = "gemini-flash-latest"):
        self.api_keys = [k.strip() for k in api_keys if k and k.strip() and k.strip() != "YOUR_GEMINI_API_KEY"]
        self.current_key_index = 0
        self.model_name = model_name
        self.memory: List[str] = []  # Rolling contextual working memory (last 5 decisions/scans)
        # Per-key state tracking: cooldown down_until timestamp, failure count, last_error
        self._key_states = {
            k: {"down_until": 0.0, "failures": 0, "last_error": ""}
            for k in self.api_keys
        }
        self.clients = {}
        self._init_all_clients()

    def _init_all_clients(self):
        """Pre-initializes genai.Client for each key in pool."""
        self.clients.clear()
        for idx, key in enumerate(self.api_keys):
            try:
                self.clients[key] = genai.Client(api_key=key)
            except Exception as e:
                logger.warning(f"[KEY_INIT_WARN] Failed to instantiate client for key index {idx + 1}: {e}")

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

    def _get_ordered_keys(self) -> List[str]:
        """
        Orders keys with Round-Robin distribution across calls while prioritizing healthy keys
        over keys currently cooling down (inspired by disbotai pool router).
        """
        import time
        now = time.monotonic()
        healthy = [k for k in self.api_keys if self._key_states[k]["down_until"] <= now]
        cooling = [
            k for k in self.api_keys 
            if self._key_states[k]["down_until"] > now and "401" not in self._key_states[k]["last_error"]
        ]

        # If all healthy keys are exhausted, fallback to usable cooling keys (soonest to expire first)
        if not healthy:
            cooling.sort(key=lambda k: self._key_states[k]["down_until"])
            return cooling

        # Round-Robin shift so we don't hammer the exact same key first every cycle
        start_idx = self.current_key_index % len(healthy)
        self.current_key_index = (self.current_key_index + 1) % len(healthy)
        ordered_healthy = healthy[start_idx:] + healthy[:start_idx]
        return ordered_healthy + cooling

    def _record_key_failure(self, key: str, reason: str):
        """Quarantines key with adaptive cooldown depending on error type."""
        import time
        state = self._key_states[key]
        state["failures"] += 1
        state["last_error"] = str(reason)[:100]
        masked = key[:6] + "..." + key[-4:] if len(key) >= 10 else "***"

        err_lower = str(reason).lower()
        if "401" in err_lower or "403" in err_lower or "api_key_invalid" in err_lower:
            # Permanent quarantine (24 hours) for invalid keys
            state["down_until"] = time.monotonic() + 86400.0
            logger.error(f"[KEY_QUARANTINE_PERMANENT] Key ({masked}) invalid or unauthorized: {reason}. Quarantined for 24h.")
        elif "429" in err_lower or "resource_exhausted" in err_lower or "quota" in err_lower:
            # Quota or rate-limit: 60s cooldown if per-minute rate limit, 300s if daily limit
            cooldown = 300.0 if "daily" in err_lower or "day" in err_lower else 60.0
            state["down_until"] = time.monotonic() + cooldown
            logger.warning(f"[KEY_QUARANTINE_429] Key ({masked}) hit quota/rate limit: {reason}. Cooldown {cooldown}s -> Rotating key pool.")
        else:
            # Temporary network / server outage (503 / timeout)
            cooldown = 30.0
            state["down_until"] = time.monotonic() + cooldown
            logger.warning(f"[KEY_QUARANTINE_TEMP] Key ({masked}) failed with {reason}. Cooldown {cooldown}s.")

    def _record_key_success(self, key: str):
        """Resets failures on successful call."""
        if key in self._key_states:
            self._key_states[key]["failures"] = 0
            self._key_states[key]["last_error"] = ""

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
            "You are a dual-domain expert: a Senior Global Macroeconomist & Central Bank Analyst, combined with an elite Quantitative Forex & Commodities Algorithmic Trader. "
            "You synthesize fundamental economic forces (US Dollar Index / DXY, Treasury Yields, Inflation/CPI/PPI, Central Bank Interest Rate trajectory) "
            "with high-precision Price Action, Multi-Timeframe Alignment, and Computer Vision. "
            "You understand Intermarket Relationships: "
            "- A surging US Dollar (DXY) and rising 10-year Treasury yields create severe headwinds for Gold (XAUUSD), discouraging aggressive BUY entries. "
            "- A softening Dollar, falling yields, or geopolitical safe-haven demand accelerates Gold rallies. "
            "You strictly adhere to risk-to-reward ratios (minimum 1:1.5). "
            "DO NOT panic-close active positions on minor intra-bar pullbacks. "
            "When a position is active, choose 'HOLD' to let predefined mathematical SL/TP and Trailing Stop execute."
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

=== 2. GLOBAL MACROECONOMIC INTELLIGENCE & SENTIMENT (Web & Central Bank Data) ===
{web_context if web_context else 'Normal market conditions.'}

=== 3. PRICE ACTION MATRIX & RECENT STRUCTURE (Spatial Crop) ===
{chart_visual if chart_visual else 'Matrix not available'}

=== 4. MARKET TECHNICAL & QUANT DATA ===
{json.dumps(market_data, indent=2)}

Guidelines:
1. Macroeconomist Assessment (Intermarket Confluence):
   - Evaluate Section 2 (Macro Intelligence): If US Dollar (DXY) or Bond Yields are surging, DO NOT open BUY positions into resistance.
   - If Macro sentiment is clearly Bearish for Gold, only consider High-Probability SELL setups or 'HOLD'.
2. Multi-Timeframe Confluence Rule (CRITICAL):
   - Check 'multi_timeframe_alignment' in technical data (M1, M5, M15, H1).
   - If macro bias is CONFLICTED / MIXED, be extremely conservative and prefer 'HOLD'.
   - NEVER BUY if M15 and H1 are strongly BEARISH, and NEVER SELL if M15 and H1 are strongly BULLISH (unless there is a massive reversal rejection wick at key Pivot levels).
2. 4 DISTINCT TRADING PLAYBOOKS (Execute the setup that matches the current regime):
   --- PLAYBOOK A: Trend Following on EMA Pullback (London & US Sessions) ---
   - Condition: Clear trend in M5/M15 (EMA 9 > 21 > 50 for Bullish, or 9 < 21 < 50 for Bearish).
   - Entry: Wait for M1 price to pullback and test dynamic EMA 9 or EMA 21. Enter on rejection wick in the trend direction.
   - SL: Beyond recent swing low/high or EMA 50. TP: 1.5x - 2.5x RR.

   --- PLAYBOOK B: Range-Bound Mean Reversion (Asian Session / Sideways Regime) ---
   - Condition: Market is in ASIAN_SESSION or EMA trend is SIDEWAYS (Price oscillating between Support and Resistance).
   - Entry: BUY at Support / S1 / S2 with bullish Pinbar/Wick. SELL at Resistance / R1 / R2 with bearish rejection wick.
   - Target: Opposite boundary or Central Pivot Point (Mean Reversion).

   --- PLAYBOOK C: Smart Money FVG Fill & Mitigation ---
   - Condition: Active Fair Value Gap (Bullish_FVG or Bearish_FVG) exists in 'fair_value_gap'.
   - Entry: Price retraces back into the FVG zone to rebalance liquidity. When price taps the FVG and rejects, execute in the direction of the original impulse.
   - Advantage: Extremely tight SL (just outside the FVG box) and massive Risk-to-Reward ratio (1:2 to 1:3).

   --- PLAYBOOK D: Liquidity Sweep / Fakeout Reversal (Stop Hunt) ---
   - Condition: Price punches through a previous High or Low by a small margin, but immediately snaps back inside with a massive wick (False Breakout).
   - Entry: Fade the fakeout! If price pierced Resistance then closed back below, execute SELL. If price spiked below Support then closed back above, execute BUY.
   - In 'reasoning', explicitly state which Playbook (A, B, C, or D) you are executing!
7. Fair Value Gap (FVG / Smart Money Imbalance):
   - Check 'fair_value_gap' in market data.
   - When an active Bullish FVG exists below current price, wait for the market to retrace and fill the gap (Mean-Reversion) before executing BUY. Do NOT buy above an unfilled imbalance.
   - When an active Bearish FVG exists above current price, wait for the market to retrace up into the gap before executing SELL.
8. Session Timing & Liquidity Guidance:
   - Check 'market_session' in market data.
   - During 'US_LONDON_OVERLAP' or 'LONDON_SESSION': High liquidity permits clean breakout and trend-following entries.
   - During 'DEAD_ZONE_TWILIGHT' or 'LATE_US_SESSION': Volatility drops and false breakouts spike. Be extremely defensive, do not enter without multiple confluences, and default to 'HOLD'.
9. Overextension & Exhaustion Protection (STRICT):
   - NEVER BUY if RSI(14) > 68 or if price is extended far above EMA 21. This indicates an exhausted climax/top.
   - NEVER SELL if RSI(14) < 32 or if price is extended far below EMA 21. This indicates an oversold floor/bottom.
   - In M1 Scalping, only BUY after a confirmed Pullback/Retest of EMA 9 or EMA 21 with lower rejection wicks.
   - In M1 Scalping, only SELL after a confirmed Pullback/Rally into EMA 9 or EMA 21 with upper rejection wicks.
10. M1 Scalping Discipline (CRITICAL):
   - NEVER chase an extended green impulse candle at the high of the day/range (Do not BUY tops).
   - NEVER chase an extended red impulse candle at the low of the day/range (Do not SELL bottoms).
   - Enter only on confirmed Pullbacks into Dynamic EMA (9/21) or Rejection Wick / Pinbar candle closes at Support/Resistance.
   - In choppy, range-bound whipsaws or breaking news, choose 'HOLD'.
"""

        ordered_keys = self._get_ordered_keys()
        if not ordered_keys:
            logger.error("[ERROR] No valid Gemini API keys configured or available.")
            return None

        for key_idx, current_key in enumerate(ordered_keys):
            client = self.clients.get(current_key)
            if client is None:
                try:
                    client = genai.Client(api_key=current_key)
                    self.clients[current_key] = client
                except Exception as e:
                    self._record_key_failure(current_key, str(e))
                    continue

            masked = current_key[:6] + "..." + current_key[-4:] if len(current_key) >= 10 else "***"
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

                models_to_try = [self.model_name, "gemini-3.8-flash", "gemini-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash"]
                last_exc = None
                response = None
                for m in models_to_try:
                    try:
                        response = client.models.generate_content(
                            model=m,
                            contents=contents_payload,
                            config=types.GenerateContentConfig(**gen_config),
                        )
                        break
                    except Exception as err:
                        last_exc = err
                        err_str = str(err)
                        if "503" in err_str or "UNAVAILABLE" in err_str:
                            continue
                        # If specific model exhausted its daily limit, fallback to next model
                        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                            logger.warning(f"[MODEL_QUOTA_FALLBACK] Model {m} quota exhausted (429) on key ({masked}). Falling back to next model...")
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
                
                # Success: reset failure counts and cooldown for this key
                self._record_key_success(current_key)

                # Record to working memory for sequential continuity
                mem_entry = f"[{timeframe}] Action: {signal.action} (Conf: {signal.confidence:.2f}) | {signal.reasoning[:120]}..."
                self.record_memory(mem_entry)

                logger.info(f"[ANALYSIS] [{symbol} {timeframe}] Key ({masked}) | Decision: {signal.action} (Confidence: {signal.confidence:.2f}) | {signal.reasoning}")
                return signal
            except Exception as e:
                err_msg = str(e)
                logger.warning(f"[API_WARN] Key ({masked}) encountered error: {err_msg}")
                self._record_key_failure(current_key, err_msg)
                continue

        logger.error("[ERROR] All Gemini API keys exhausted or in cooldown.")
        return None
