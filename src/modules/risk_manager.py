"""
ATRX Risk Manager — Anti-Martingale Position Sizing Engine

Philosophy:
    Opposite of Martingale: REDUCE position sizes as drawdown increases.
    This protects capital during losing streaks and allows recovery
    without catastrophic losses.

Features:
    - Persistent state (survives restarts)
    - Drawdown-tiered risk multipliers
    - Daily and total drawdown circuit breakers
    - Open exposure tracking per ticket
    - Daily auto-reset
"""

import json
import os
import logging
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Tuple, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

LAGOS_TZ = ZoneInfo("Africa/Lagos")


class RiskManager:
    """
    Anti-Martingale Risk Engine.
    
    Drawdown-based risk scaling:
    
    | Drawdown Level | Risk Multiplier | Mode            |
    |----------------|-----------------|-----------------|
    | 0–1%           | 100%            | Normal          |
    | 1–2%           | 75%             | Early caution   |
    | 2–3%           | 50%             | Defensive       |
    | 3%+            | 25%             | Survival        |
    
    This means a system configured for 0.50% base risk per trade
    will automatically scale down to 0.125% per trade when in
    survival mode — preserving capital for recovery.
    """

    # Drawdown-based risk multiplier thresholds
    DD_RISK_TIERS = [
        (1.0, 1.00),           # 0-1% DD → full risk
        (2.0, 0.75),           # 1-2% DD → 75%
        (3.0, 0.50),           # 2-3% DD → 50%
        (float("inf"), 0.25),  # 3%+  DD → survival mode
    ]

    def __init__(self, state_file: str = "risk_state.json",
                 max_daily_dd: float = 0.038,
                 max_total_dd: float = 0.08):
        self.state_file = state_file
        self.max_daily_drawdown = max_daily_dd   # 3.8% hard stop
        self.max_total_drawdown = max_total_dd   # 8.0% max drawdown
        self.max_leverage = 30.0

        self.state = self._load_state()
        logger.info(
            f"Risk Manager Loaded. Equity: ${self.state['current_capital']:.2f} "
            f"| Peak: ${self.state['peak_capital']:.2f}"
        )

    # ─── STATE PERSISTENCE ─────────────────────

    def _load_state(self) -> dict:
        default_state = {
            "current_capital": 0.0,
            "peak_capital": 0.0,
            "daily_start_capital": 0.0,
            "open_risk_pct": 0.0,
            "open_risk_by_ticket": {},
            "timestamp": datetime.now(LAGOS_TZ).isoformat(),
        }
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    data = json.load(f)
                # Reset daily tracking if new day
                last_date = (
                    datetime.fromisoformat(data["timestamp"])
                    .astimezone(LAGOS_TZ)
                    .date()
                )
                if last_date < datetime.now(LAGOS_TZ).date():
                    data["daily_start_capital"] = data.get("current_capital", 0.0)
                    data["open_risk_pct"] = 0.0
                    data["open_risk_by_ticket"] = {}
                return {**default_state, **data}
            except Exception as e:
                logger.warning(f"Failed to load risk state: {e}")
        return default_state

    def save_state(self):
        self.state["timestamp"] = datetime.now(LAGOS_TZ).isoformat()
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save risk state: {e}")

    # ─── DRAWDOWN CALCULATIONS ─────────────────

    def get_drawdown_pct(self) -> float:
        """Current drawdown from peak capital as a percentage."""
        peak = self.state["peak_capital"]
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - self.state["current_capital"]) / peak)

    def get_daily_drawdown_pct(self) -> float:
        """Today's drawdown from start-of-day capital."""
        start = self.state["daily_start_capital"]
        if start <= 0:
            return 0.0
        return max(0.0, (start - self.state["current_capital"]) / start)

    def get_risk_multiplier(self) -> float:
        """Anti-martingale: reduce risk as drawdown increases."""
        dd_pct = self.get_drawdown_pct() * 100  # Convert to percentage
        for threshold, multiplier in self.DD_RISK_TIERS:
            if dd_pct < threshold:
                return multiplier
        return 0.25  # Fallback: survival mode

    # ─── CIRCUIT BREAKERS ──────────────────────

    def check_circuit_breakers(self) -> Tuple[bool, str]:
        """Returns (can_trade, reason). False = halt trading."""
        daily_dd = self.get_daily_drawdown_pct()
        total_dd = self.get_drawdown_pct()

        if daily_dd >= self.max_daily_drawdown:
            return False, f"DAILY DD LIMIT ({daily_dd:.2%} >= {self.max_daily_drawdown:.2%})"

        if total_dd >= self.max_total_drawdown:
            return False, f"TOTAL DD LIMIT ({total_dd:.2%} >= {self.max_total_drawdown:.2%})"

        return True, "OK"

    # ─── POSITION SIZING ──────────────────────

    def calculate_position_size(self, balance: float, risk_pct: float,
                                sl_distance: float, point_value: float,
                                symbol_info: Any = None) -> float:
        """
        ATR-based position sizing with anti-martingale scaling.
        
        Formula:
            risk_amount = balance × risk_pct × risk_multiplier
            lots = risk_amount / (sl_distance × point_value)
        
        Then clamped to leverage limits and broker min/max lot constraints.
        """
        if sl_distance <= 0 or point_value <= 0:
            return 0.0

        multiplier = self.get_risk_multiplier()
        effective_risk = risk_pct * multiplier
        risk_amount = balance * effective_risk

        raw_lots = risk_amount / (sl_distance * point_value)

        # Apply leverage limit
        if symbol_info:
            price = getattr(symbol_info, "ask", 1.0)
            contract_size = getattr(symbol_info, "trade_contract_size", 100000)
            max_lots = (balance * self.max_leverage) / (price * contract_size)
            raw_lots = min(raw_lots, max_lots)

            # Broker constraints
            min_lot = getattr(symbol_info, "volume_min", 0.01)
            max_lot = getattr(symbol_info, "volume_max", 100.0)
            step = getattr(symbol_info, "volume_step", 0.01)

            raw_lots = max(min_lot, min(raw_lots, max_lot))
            if step > 0:
                raw_lots = math.floor(raw_lots / step) * step

        return round(raw_lots, 2)

    # ─── EQUITY UPDATES ───────────────────────

    def update_equity(self, equity: float):
        """Called each cycle with current account equity."""
        self.state["current_capital"] = equity
        if equity > self.state["peak_capital"]:
            self.state["peak_capital"] = equity
        if self.state["daily_start_capital"] <= 0:
            self.state["daily_start_capital"] = equity
        self.save_state()

    # ─── OPEN EXPOSURE TRACKING ────────────────

    def register_open_risk(self, ticket: int, risk_pct: float):
        """Track risk allocated to an open position."""
        self.state["open_risk_by_ticket"][str(ticket)] = risk_pct
        self.state["open_risk_pct"] = sum(self.state["open_risk_by_ticket"].values())
        self.save_state()

    def release_risk(self, ticket: int):
        """Release risk when a position closes."""
        self.state["open_risk_by_ticket"].pop(str(ticket), None)
        self.state["open_risk_pct"] = sum(self.state["open_risk_by_ticket"].values())
        self.save_state()

    def get_available_risk(self, max_total_risk: float = 0.10) -> float:
        """How much risk budget remains for new positions."""
        return max(0.0, max_total_risk - self.state["open_risk_pct"])
