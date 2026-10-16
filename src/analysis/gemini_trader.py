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

    def analyze(self, symbol: str, timeframe: str, market_data: dict, current_position: Optional[str] = None, chart_visual: str = "", web_context: str = "", local_scan_note: str = "", image_path: Optional[str] = None, adaptive_memory: str = "") -> Optional[TradeSignal]:
        """
        Sends structured market technical summary + Fast Memory + Adaptive Trade Journal + Real Screenshot Image to Gemini Vision.
        Extracts strictly-typed trade signal using google-genai structured output.
        Automatically switches to next API key if quota limit or error occurs.
        """
        if not self.api_keys:
            logger.error("[ERROR] No valid Gemini API keys configured.")
            return None

        system_instruction = (
            "You are an Elite Institutional Trading Council consisting of FOUR specialized master minds working in perfect synergy:\n"
            "1. THE PREDICTIVE NEWS & PRE-EVENT RISK ASSESSOR: A specialist who pulls upcoming unreleased daily news (Red, Orange, Yellow) from the economic calendar, tracks the countdown to release, and evaluates pre-event environmental conditions (Liquidity Squeeze, Spread Expansion, Institutional Pre-Positioning, or Front-Running). You brief the council on what is brewing BEFORE the news lands.\n"
            "2. THE HIGH-PRECISION TECHNICAL ANALYST: A master of Price Action, Market Structure Shift (MSS), Rejection Wicks, Liquidity Sweeps, and Order Blocks. You pinpoint exact entry trigger timing down to the sub-millisecond candle close and demand high-probability execution.\n"
            "3. THE APPLIED MATHEMATICAL QUANT: A disciplined mathematical risk theorist specializing in Kelly Criterion, ATR-based Stop Loss volatility buffers, Expected Value (EV), and asymmetric Risk-to-Reward distribution (minimum 1:1.5 to 1:3). You calculate odds coldly and ruthlessly veto trades with negative mathematical expectancy.\n"
            "4. THE GLOBAL MACROECONOMIST & CENTRAL BANK ANALYST: A macro strategist tracking central bank policy trajectories, Intermarket flows (US Dollar DXY, 10Y Treasury Yields, Inflation CPI/PPI, Geopolitical Risk), and released economic statistics. You ensure trades never fight macro tides.\n\n"
            "DECISION PROTOCOL:\n"
            "- A signal (BUY or SELL) is only approved if all 4 perspectives achieve UNANIMOUS CONFLUENCE.\n"
            "- If the Pre-Event Assessor warns that a Red-Folder release is imminent within 60 minutes and environment is unpredictable, the council MUST vote 'HOLD' (unless executing Playbook F News Breakout with tight trailing SL).\n"
            "- If the Macroeconomist warns of headwind, the Mathematician calculates inadequate RR (< 1.5), or the Technical Analyst spots an exhausted climax/overextension, the council MUST vote 'HOLD'.\n"
            "- When an active position is open, default to 'HOLD' to let mathematical Trailing Stops and Fast Break-Even execute."
        )

        memory_context = self.get_memory_context()

        prompt = f"""
Analyze the current market condition and provide trading decision for:
- Asset: {symbol}
- Timeframe: {timeframe}
- Current Active Position: {current_position if current_position else 'None'}
- Local Scanner Trigger Note: {local_scan_note if local_scan_note else 'Regular Candle Scan'}

=== 1. AI SHORT-TERM WORKING MEMORY (Recent Decisions & Cycle Buffer) ===
{memory_context}

=== 2. ADAPTIVE LONG-TERM TRADE JOURNAL (Past Real Trade Lessons & Reflections) ===
{adaptive_memory if adaptive_memory else 'No previous closed trades recorded yet (Clean slate).'}

=== 3. GLOBAL MACROECONOMIC INTELLIGENCE & SENTIMENT (Web & Central Bank Data) ===
{web_context if web_context else 'Normal market conditions.'}

=== 4. PRICE ACTION MATRIX & RECENT STRUCTURE (Spatial Crop) ===
{chart_visual if chart_visual else 'Matrix not available'}

=== 4. MARKET TECHNICAL & QUANT DATA ===
{json.dumps(market_data, indent=2)}

INSTITUTIONAL COUNCIL EVALUATION GUIDELINES:
1. Predictive News & Pre-Event Assessor Assessment:
   - Check [PREDICTIVE_NEWS_ASSESSOR] in Section 2: Look at the countdown to upcoming unreleased news.
   - If a Red Folder event is within 30-60 minutes, evaluate if the market is contracting in pre-news consolidation or hunting liquidity. If risk is high, recommend 'HOLD'.
2. Macroeconomist Assessment (Fundamental & Intermarket Confluence):
   - Assess ForexFactory releases & DXY/Yields. If Dollar is surging or Treasury yields spike, forbid BUY on Gold/EURUSD.
   - If Macro sentiment is Bearish, approve only High-Probability SELL setups or 'HOLD'.
3. Applied Mathematical Quant Assessment (Risk / Reward & Probability):
   - SL distance MUST be anchored outside market noise (using ATR or beyond swing points), minimum 6.0 pts.
   - Target TP must offer at least 1:1.5 RR (1.5x of SL). If structure limits TP before 1.5x, VETO the trade with 'HOLD'.
   - Evaluate Bollinger Bandwidth and ATR: during low-volatility compression, prepare for expansion; during climax exhaustion, refuse to enter.
4. High-Precision Technical Analyst Assessment (Structure & Confirmation):
   - Check 'multi_timeframe_alignment' in technical data (M1, M5, M15, H1).
   - If macro bias is CONFLICTED / MIXED, veto entry and select 'HOLD'.
   - NEVER BUY if M15/H1 are strongly BEARISH, and NEVER SELL if M15/H1 are strongly BULLISH.
   - Verify Candlestick confirmation: Rejecting pinbars, rejection wicks at key Support/Resistance/Order Blocks.
3. 6 ELITE TRADING PLAYBOOKS (Execute the setup that matches the current regime):
   --- PLAYBOOK A: Trend Following on EMA Pullback (London & US Sessions) ---
   - Condition: Clear trend in M5/M15 (EMA 9 > 21 > 50 for Bullish, or 9 < 21 < 50 for Bearish).
   - Entry: Wait for M1 price to pullback and test dynamic EMA 9 or EMA 21. Enter on rejection wick in the trend direction.
   - SL: Beyond recent swing low/high or EMA 50. TP: 1.5x - 2.5x RR.

   --- PLAYBOOK B: Range-Bound Mean Reversion (Asian Session / Sideways Regime) ---
   - Condition: Market is in ASIAN_SESSION or EMA trend is SIDEWAYS (Price oscillating between Support and Resistance).
   - Entry: BUY at Support / S1 / S2 / Lower Bollinger Band with bullish Pinbar/Wick. SELL at Resistance / R1 / R2 / Upper Bollinger Band with bearish rejection wick.
   - Target: Opposite boundary or Central Pivot Point (Mean Reversion).

   --- PLAYBOOK C: Smart Money FVG Fill & Mitigation ---
   - Condition: Active Fair Value Gap (Bullish_FVG or Bearish_FVG) exists in 'fair_value_gap'.
   - Entry: Price retraces back into the FVG zone to rebalance liquidity. When price taps the FVG and rejects, execute in the direction of the original impulse.
   - Advantage: Extremely tight SL (just outside the FVG box) and massive Risk-to-Reward ratio (1:2 to 1:3).

   --- PLAYBOOK D: Liquidity Sweep / Fakeout Reversal (Stop Hunt) ---
   - Condition: Price punches through Buy-Side Liquidity (BSL) or Sell-Side Liquidity (SSL) by a small margin, but immediately snaps back inside with a massive wick (False Breakout).
   - Entry: Fade the fakeout! If price pierced Resistance then closed back below, execute SELL. If price spiked below Support then closed back above, execute BUY.

   --- PLAYBOOK E: Institutional Order Block (OB) Retest ---
   - Condition: An active unmitigated Order Block exists in 'order_block'.
   - Entry: Price retraces back into the Order Block zone (last down-candle before up-impulse for BUY, or last up-candle before down-impulse for SELL). Enter on rejection wick inside the block.
   - Advantage: Institutional footprint entry with high conviction.

   --- PLAYBOOK F: Volatility Squeeze & News Breakout (Bollinger Band Expansion) ---
   - Condition: Bollinger Bandwidth was compressed (< 0.15%) then price aggressively expands outside the Upper or Lower Band with a large impulse body.
   - Entry: Ride the explosive expansion! BUY on upper breakout if EMA trend is Bullish; SELL on lower breakdown if EMA trend is Bearish.

   - In 'reasoning', explicitly state which Playbook (A, B, C, D, E, or F) you are executing!

4. Liquidity Pool & Structure Confluence:
   - Check 'liquidity_pools' and 'fair_value_gap' in market data.
   - Do NOT enter BUY directly under an un-swept Buy-Side Liquidity pool or unfilled Bearish FVG.
   - Do NOT enter SELL directly above an un-swept Sell-Side Liquidity pool or unfilled Bullish FVG.
5. Session Timing & Liquidity Guidance:
   - Check 'market_session' in market data.
   - During 'US_LONDON_OVERLAP' or 'LONDON_SESSION': High liquidity permits clean breakout and trend-following entries.
   - During 'DEAD_ZONE_TWILIGHT' or 'LATE_US_SESSION': Volatility drops and false breakouts spike. Be extremely defensive, do not enter without multiple confluences, and default to 'HOLD'.
6. Multi-Timeframe Overbought / Oversold Cascading Hierarchy (H1 -> M15 -> M5 -> M1):
   - Check 'multi_timeframe_alignment.macro_exhaustion' and 'exhaustion_state' of H1/M15/M5/M1.
   - If H1 or M15 is OVERBOUGHT (RSI >= 70): Strictly FORBID any BUY on M1! Higher timeframe buyers are exhausted and smart money is preparing to distribute/dump. Only look for SELL rejection setups or 'HOLD'.
   - If H1 or M15 is OVERSOLD (RSI <= 30): Strictly FORBID any SELL on M1! Higher timeframe sellers are depleted and smart money is accumulating. Only look for BUY reversal sweeps or 'HOLD'.
   - Local M1 Scalping Exhaustion: Even if macro is balanced, NEVER BUY if M1 RSI(14) > 68 or extended far above EMA 21 (Wait for pullback to EMA 9/21). NEVER SELL if M1 RSI(14) < 32 or extended far below EMA 21.
7. M1 Scalping Discipline (CRITICAL):
   - NEVER chase an extended green impulse candle at the high of the day/range (Do not BUY tops).
   - NEVER chase an extended red impulse candle at the low of the day/range (Do not SELL bottoms).
   - Enter only on confirmed Pullbacks into Dynamic EMA (9/21) or Rejection Wick / Pinbar candle closes at Support/Resistance.
   - In choppy, range-bound whipsaws without clear playbook alignment, choose 'HOLD'.
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

                models_to_try = [
                    self.model_name,
                    "gemini-3.7-flash",
                    "gemini-3.5-flash",
                    "gemini-flash-lite-latest",
                    "gemini-3.5-flash-lite",
                    "gemini-3.1-flash-lite",
                ]
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
