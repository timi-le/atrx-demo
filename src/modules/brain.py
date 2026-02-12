"""
ATRX GeminiBrain — Three-Tier LLM Decision Engine

Architecture:
  Tier 1: Pre-Filter  (Gemini Flash)  — Quick worthiness gate (~$0.001/call)
  Tier 2: Entry        (Gemini Pro)    — Full BUY/SELL/HOLD with reasoning
  Tier 3: PM Confirm   (Gemini Pro)    — Portfolio-level approve/veto

Key Design Principle:
  The AI VALIDATES quantitative signals — it never overrides alpha direction.
  If the alpha stack says bullish, Gemini cannot recommend SELL.

NOTE: This is the public/demo version. Production prompts, confidence
calibration, and cost-optimization logic are not included.
"""

import json
import logging
import re
import time
from typing import Any, Dict, Optional, Literal
from dataclasses import dataclass

import google.generativeai as genai

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────

def _safe_json_extract(text: str) -> Optional[Dict[str, Any]]:
    """Extract first JSON object from potentially noisy LLM output."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


# ─────────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────────

@dataclass
class PreFilterResult:
    """Result from Tier 1 pre-filter."""
    worthy: bool
    confidence: float
    reason: str
    raw_response: Optional[Dict[str, Any]] = None


@dataclass
class EntryDecision:
    """Result from Tier 2 entry decision."""
    action: Literal["BUY", "SELL", "HOLD"]
    risk_percentage: float
    stop_loss: float
    take_profit: float
    confidence: float
    reasoning: str
    plan: Optional[str] = None
    management_action: str = "NONE"
    direction_aligned: bool = True


@dataclass
class PMConfirmation:
    """Result from Tier 3 portfolio confirmation."""
    approved: bool
    adjusted_risk: Optional[float] = None
    reason: str = ""
    portfolio_action: str = "NONE"


# ─────────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────────

class _RateLimiter:
    """Per-tier rate limiting to respect Gemini API quotas."""

    def __init__(self, calls_per_minute: int = 15):
        self._calls_per_minute = calls_per_minute
        self._timestamps: list = []

    def wait_if_needed(self):
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < 60]
        if len(self._timestamps) >= self._calls_per_minute:
            sleep_time = 60 - (now - self._timestamps[0])
            if sleep_time > 0:
                logger.info(f"Rate limit: sleeping {sleep_time:.1f}s")
                time.sleep(sleep_time)
        self._timestamps.append(time.time())


# ─────────────────────────────────────────────
# GEMINI BRAIN — THREE-TIER ARCHITECTURE
# ─────────────────────────────────────────────

class GeminiBrain:
    """
    Three-tier LLM decision engine using Google Gemini.
    
    The brain operates under a strict constraint: it can never contradict
    the quantitative alpha direction. This prevents LLM hallucination
    from overriding systematic edge.
    
    Tier 1 (Pre-Filter):
        Uses Gemini Flash for sub-second candidate screening.
        Input: alpha score, basic market context
        Output: worthy (bool), confidence (0-1)
        
    Tier 2 (Entry Decision):
        Uses Gemini Pro for comprehensive trade analysis.
        Input: full alpha packet, macro context, news overlay
        Output: BUY/SELL/HOLD, risk sizing, SL/TP levels
        Constraint: action MUST align with alpha_direction sign
        
    Tier 3 (PM Confirmation):
        Uses Gemini Pro for portfolio-level gate.
        Input: proposed trade + current portfolio state
        Output: approve/reduce/veto
        
    Cost Optimization:
        Tier 1 filters ~60% of candidates at <$0.001 each,
        preventing expensive Tier 2/3 calls on weak setups.
    """

    def __init__(self, api_key: str = None):
        if api_key:
            genai.configure(api_key=api_key)

        # Model configuration (tier → model mapping)
        self._models = {
            "prefilter": "gemini-2.0-flash",      # Fast, cheap gate
            "entry": "gemini-2.5-pro",             # Full analysis
            "pm": "gemini-2.5-pro",                # Portfolio confirmation
        }

        # Rate limiters per tier
        self._limiters = {
            "prefilter": _RateLimiter(calls_per_minute=30),
            "entry": _RateLimiter(calls_per_minute=15),
            "pm": _RateLimiter(calls_per_minute=15),
        }

    # ─── TIER 1: PRE-FILTER ────────────────────

    def prefilter(self, symbol: str, alpha_score: float, 
                  trend: str, session: str) -> PreFilterResult:
        """Quick worthiness check — should we spend a Pro call on this?"""
        self._limiters["prefilter"].wait_if_needed()

        # [Production prompt not included]
        # The pre-filter receives: symbol, alpha score, trend context, session
        # Returns: structured JSON with worthy (bool) and confidence (0-1)
        
        raise NotImplementedError(
            "Production pre-filter prompt not included in public version. "
            "See architecture documentation for the design pattern."
        )

    # ─── TIER 2: ENTRY DECISION ────────────────

    def get_entry_decision(self, symbol: str, alpha_packet: dict,
                           macro_context: dict, news_overlay: dict = None,
                           open_positions: list = None) -> EntryDecision:
        """
        Full entry analysis with directional constraint enforcement.
        
        CRITICAL: If alpha_direction > 0, only BUY is allowed.
                  If alpha_direction < 0, only SELL is allowed.
                  AI can always say HOLD, but cannot contradict direction.
        """
        self._limiters["entry"].wait_if_needed()

        alpha_direction = alpha_packet.get("alpha_direction", 0.0)

        # [Production prompt not included]
        # The entry decision receives the full alpha packet, macro trends,
        # news context, and current positions. It returns structured JSON
        # with action, risk_percentage, stop_loss, take_profit, reasoning.

        # ── DIRECTIONAL CONSTRAINT ENFORCEMENT ──
        # This is the key innovation: post-process the AI response
        # to ensure it never contradicts the quantitative signal.
        #
        # if alpha_direction > 0 and decision.action == "SELL":
        #     decision.action = "HOLD"
        #     decision.reasoning += " [BLOCKED: contradicts bullish alpha]"
        #
        # if alpha_direction < 0 and decision.action == "BUY":
        #     decision.action = "HOLD"  
        #     decision.reasoning += " [BLOCKED: contradicts bearish alpha]"

        raise NotImplementedError(
            "Production entry prompt not included in public version. "
            "See architecture documentation for the constraint enforcement pattern."
        )

    # ─── TIER 3: PM CONFIRMATION ───────────────

    def confirm_with_pm(self, proposed_trade: dict, 
                        portfolio_state: dict) -> PMConfirmation:
        """
        Portfolio-manager level gate — considers correlation,
        total exposure, drawdown state, and stop-wave risk.
        
        Can: approve, reduce position size, or veto entirely.
        """
        self._limiters["pm"].wait_if_needed()

        # [Production prompt not included]
        # The PM receives: proposed trade details, current portfolio
        # (all open positions with P&L), drawdown metrics, and 
        # correlation exposure. Returns approve/reduce/veto.

        raise NotImplementedError(
            "Production PM prompt not included in public version. "
            "See architecture documentation for portfolio-level gate design."
        )

    # ─── HELPERS ───────────────────────────────

    def _call_gemini(self, tier: str, prompt: str, 
                     system_instruction: str = None) -> Optional[Dict]:
        """Generic Gemini API call with error handling and JSON extraction."""
        try:
            model = genai.GenerativeModel(
                self._models[tier],
                system_instruction=system_instruction,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1,  # Low temperature for consistent decisions
                ),
            )
            response = model.generate_content(prompt)
            return _safe_json_extract(response.text)
        except Exception as e:
            logger.error(f"Gemini {tier} call failed: {e}")
            return None
