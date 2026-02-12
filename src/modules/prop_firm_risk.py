"""
ATRX Prop Firm Risk Manager — "Never Fail" Risk Architecture

Phase-aware risk budgeting for prop firm challenges:
  Challenge    → Aggressive but controlled (0.50-1.25% per trade)
  Verification → Conservative (0.25-0.75% per trade)
  Funded       → Capital preservation (0.25-1.00% per trade)
  Scaled       → Optimized for AUM growth

Features:
  - Currency correlation tracking (EURUSD + GBPUSD = shared USD exposure)
  - Dynamic position limits based on available risk budget
  - Drawdown circuit breakers (daily + trailing)
  - Profit banking with configurable targets
  - Phase-dependent risk bounds
"""

import json
import os
import logging
import math
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone, date
from enum import Enum

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# ENUMS
# ─────────────────────────────────────────────

class DrawdownType(str, Enum):
    STATIC = "static"     # DD measured from initial balance
    TRAILING = "trailing"  # DD measured from high-water mark


class TradingPhase(str, Enum):
    CHALLENGE = "challenge"
    VERIFICATION = "verification"
    FUNDED = "funded"
    SCALED = "scaled"


class RiskAction(str, Enum):
    ALLOW = "allow"
    REDUCE_SIZE = "reduce_size"
    BLOCK_NEW = "block_new"
    HALT_TRADING = "halt_trading"


# ─────────────────────────────────────────────
# CURRENCY EXPOSURE MAPPING
# ─────────────────────────────────────────────

SYMBOL_CURRENCY_EXPOSURE = {
    # FX Majors
    "EURUSD": {"EUR": 1.0, "USD": -1.0},
    "GBPUSD": {"GBP": 1.0, "USD": -1.0},
    "AUDUSD": {"AUD": 1.0, "USD": -1.0},
    "NZDUSD": {"NZD": 1.0, "USD": -1.0},
    "USDCAD": {"USD": 1.0, "CAD": -1.0},
    "USDCHF": {"USD": 1.0, "CHF": -1.0},
    "USDJPY": {"USD": 1.0, "JPY": -1.0},
    # FX Crosses
    "EURGBP": {"EUR": 1.0, "GBP": -1.0},
    "EURJPY": {"EUR": 1.0, "JPY": -1.0},
    "GBPJPY": {"GBP": 1.0, "JPY": -1.0},
    "AUDJPY": {"AUD": 1.0, "JPY": -1.0},
    "NZDJPY": {"NZD": 1.0, "JPY": -1.0},
    # Commodities & Crypto
    "XAUUSD": {"XAU": 1.0, "USD": -1.0},
    "BTCUSD": {"BTC": 1.0, "USD": -1.0},
    "ETHUSD": {"ETH": 1.0, "USD": -1.0},
}


# ─────────────────────────────────────────────
# PHASE CONFIGURATION
# ─────────────────────────────────────────────

@dataclass
class PhaseConfig:
    """Risk parameters for each trading phase."""
    phase: TradingPhase
    dd_type: DrawdownType
    max_daily_dd_pct: float
    max_total_dd_pct: float
    min_risk_per_trade: float
    max_risk_per_trade: float
    profit_target_pct: float  # 0 = no target (funded)


PHASE_CONFIGS = {
    TradingPhase.CHALLENGE: PhaseConfig(
        phase=TradingPhase.CHALLENGE,
        dd_type=DrawdownType.STATIC,
        max_daily_dd_pct=0.038,
        max_total_dd_pct=0.08,
        min_risk_per_trade=0.005,
        max_risk_per_trade=0.0125,
        profit_target_pct=0.08,
    ),
    TradingPhase.VERIFICATION: PhaseConfig(
        phase=TradingPhase.VERIFICATION,
        dd_type=DrawdownType.STATIC,
        max_daily_dd_pct=0.038,
        max_total_dd_pct=0.08,
        min_risk_per_trade=0.0025,
        max_risk_per_trade=0.0075,
        profit_target_pct=0.05,
    ),
    TradingPhase.FUNDED: PhaseConfig(
        phase=TradingPhase.FUNDED,
        dd_type=DrawdownType.TRAILING,
        max_daily_dd_pct=0.038,
        max_total_dd_pct=0.08,
        min_risk_per_trade=0.0025,
        max_risk_per_trade=0.01,
        profit_target_pct=0.0,
    ),
}


# ─────────────────────────────────────────────
# POSITION AND EXPOSURE TRACKING
# ─────────────────────────────────────────────

@dataclass
class OpenPosition:
    """Tracked open position for risk calculations."""
    ticket: int
    symbol: str
    action: str  # "BUY" or "SELL"
    volume: float
    risk_pct: float
    entry_price: float
    stop_loss: float
    opened_at: str = ""


class PropFirmRiskManager:
    """
    Prop firm-aware risk management layer.
    
    Sits above the base RiskManager and adds:
    - Phase-dependent risk bounds
    - Currency correlation tracking
    - Dynamic position limits
    - Profit banking triggers
    - Drawdown-triggered de-risking
    
    The key insight: position limits are NOT static.
    max_new_positions = available_risk_budget / min_risk_per_trade
    
    This allows more positions when risk budget is healthy,
    and automatically reduces capacity as drawdown increases.
    """

    def __init__(self, phase: TradingPhase = TradingPhase.CHALLENGE,
                 initial_balance: float = 100000.0):
        self.phase = phase
        self.config = PHASE_CONFIGS[phase]
        self.initial_balance = initial_balance
        self.high_water_mark = initial_balance

        # Open position tracking
        self.open_positions: Dict[int, OpenPosition] = {}
        self._daily_pnl = 0.0

    # ─── RISK BUDGET ──────────────────────────

    def get_risk_budget(self, current_equity: float) -> Dict[str, Any]:
        """Calculate available risk budget based on current state."""
        used_risk = sum(p.risk_pct for p in self.open_positions.values())
        dd_pct = self._get_drawdown_pct(current_equity)

        # De-risk as drawdown increases
        dd_multiplier = 1.0
        if dd_pct > 0.02:
            dd_multiplier = 0.5
        elif dd_pct > 0.01:
            dd_multiplier = 0.75

        max_total_risk = self.config.max_total_dd_pct * 0.5 * dd_multiplier
        available = max(0.0, max_total_risk - used_risk)

        return {
            "available_risk_pct": available,
            "used_risk_pct": used_risk,
            "dd_multiplier": dd_multiplier,
            "max_new_positions": int(available / self.config.min_risk_per_trade)
            if available > 0 else 0,
        }

    # ─── CORRELATION CHECK ────────────────────

    def check_correlation(self, new_symbol: str, new_action: str) -> Tuple[bool, str]:
        """
        Check if a new position would create excessive currency correlation.
        
        Same-symbol averaging is ALLOWED (strategic).
        Cross-symbol correlation is checked (e.g., long EURUSD + long GBPUSD 
        = excessive USD short exposure).
        """
        new_exposure = SYMBOL_CURRENCY_EXPOSURE.get(new_symbol, {})
        if not new_exposure:
            return True, "Unknown symbol — no correlation data"

        # Aggregate existing exposure by currency
        total_exposure: Dict[str, float] = {}
        for pos in self.open_positions.values():
            if pos.symbol == new_symbol:
                continue  # Same-symbol averaging allowed
            sym_exp = SYMBOL_CURRENCY_EXPOSURE.get(pos.symbol, {})
            direction = 1.0 if pos.action == "BUY" else -1.0
            for ccy, weight in sym_exp.items():
                total_exposure[ccy] = total_exposure.get(ccy, 0.0) + weight * direction

        # Check if new trade amplifies existing exposure
        new_direction = 1.0 if new_action == "BUY" else -1.0
        for ccy, weight in new_exposure.items():
            proposed = weight * new_direction
            existing = total_exposure.get(ccy, 0.0)
            if abs(existing + proposed) > 2.0:  # Threshold: >2x exposure in one currency
                return False, f"Excessive {ccy} exposure: existing={existing:.1f}, proposed={proposed:.1f}"

        return True, "OK"

    # ─── POSITION TRACKING ────────────────────

    def open_position(self, pos: OpenPosition):
        self.open_positions[pos.ticket] = pos
        logger.info(f"PropRisk: Opened {pos.symbol} ({pos.action}) ticket={pos.ticket}")

    def close_position(self, ticket: int, realized_pnl: float):
        pos = self.open_positions.pop(ticket, None)
        if pos:
            self._daily_pnl += realized_pnl
            logger.info(f"PropRisk: Closed ticket={ticket} PnL=${realized_pnl:.2f}")

    # ─── DRAWDOWN ─────────────────────────────

    def _get_drawdown_pct(self, current_equity: float) -> float:
        if self.config.dd_type == DrawdownType.TRAILING:
            if current_equity > self.high_water_mark:
                self.high_water_mark = current_equity
            base = self.high_water_mark
        else:
            base = self.initial_balance

        if base <= 0:
            return 0.0
        return max(0.0, (base - current_equity) / base)

    # ─── RISK ACTION ──────────────────────────

    def assess_risk(self, current_equity: float) -> RiskAction:
        """Determine what risk actions are allowed given current state."""
        dd = self._get_drawdown_pct(current_equity)

        if dd >= self.config.max_total_dd_pct * 0.95:
            return RiskAction.HALT_TRADING
        if dd >= self.config.max_total_dd_pct * 0.75:
            return RiskAction.BLOCK_NEW
        if dd >= self.config.max_total_dd_pct * 0.50:
            return RiskAction.REDUCE_SIZE
        return RiskAction.ALLOW
