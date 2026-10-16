"""
Adaptive Trade Journal & Long-Term Memory Module
Inspired by disbotai's Adaptive Memory & Neural Graph architecture.
Persists past trade outcomes (Wins, Losses, False Breakouts, High-Slippage Zones),
allowing the Gemini Institutional Council to continuously learn and self-reflect
across sessions rather than starting blind.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ManusTrade.TradeJournal")

class TradeJournal:
    """
    Self-Reflective Adaptive Memory.
    Records closed trades with market context and generates lessons for Gemini AI.
    """
    def __init__(self, storage_file: str = "trade_journal.json", max_entries: int = 40):
        self.storage_file = storage_file
        self.max_entries = max_entries
        self.history: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Loads journal entries from local disk."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
                logger.info(f"[TRADE_JOURNAL] Loaded {len(self.history)} historical trade memories from {self.storage_file}")
            except Exception as e:
                logger.warning(f"[JOURNAL_LOAD_WARN] Failed to read journal file: {e}")
                self.history = []

    def _save(self):
        """Persists journal entries to disk."""
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self.history[-self.max_entries:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[JOURNAL_SAVE_WARN] Could not persist trade journal: {e}")

    def record_trade_result(
        self,
        symbol: str,
        action: str,
        profit: float,
        pips: float = 0.0,
        playbook: str = "Unknown",
        reason: str = ""
    ):
        """
        Records a completed trade outcome and generates an adaptive reflection lesson.
        """
        outcome = "WIN" if profit > 0 else ("BREAK_EVEN" if profit == 0 else "LOSS")
        
        # Derive reflective lesson for the AI
        if outcome == "LOSS":
            lesson = f"Caution on {symbol} {action}: Encountered loss ({profit:.2f}). Check for fakeouts, liquidity sweep rejection, or conflicting higher-TF bias before re-entering."
        elif outcome == "WIN":
            lesson = f"Validated confluence on {symbol} {action} (+{profit:.2f}): Playbook {playbook} executed cleanly."
        else:
            lesson = f"Fast Break-Even triggered on {symbol} {action} ({profit:.2f}): Entry protected against reversal."

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": symbol,
            "action": action,
            "outcome": outcome,
            "profit": round(profit, 2),
            "playbook": playbook,
            "lesson": lesson,
            "note": reason[:120] if reason else ""
        }

        self.history.append(entry)
        if len(self.history) > self.max_entries:
            self.history.pop(0)

        self._save()
        logger.info(f"[TRADE_JOURNAL_SAVED] [{symbol}] Outcome: {outcome} ({profit:.2f}) | Lesson: {lesson}")

    def get_adaptive_memory_brief(self, symbol: str, limit: int = 5) -> str:
        """
        Returns recent lessons specifically relevant to this symbol to embed into the Gemini prompt.
        """
        if not self.history:
            return "No previous closed trades recorded yet (Clean slate)."

        relevant = [e for e in self.history if e.get("symbol") == symbol][-limit:]
        if not relevant:
            relevant = self.history[-limit:]

        lines = []
        for r in relevant:
            lines.append(f"- [{r['timestamp']}] {r['action']} ({r['outcome']} {r['profit']}): {r['lesson']}")

        return "\n".join(lines)
