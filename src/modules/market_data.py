"""
ATRX Alpha Generation Engine — Multi-Factor Scoring Model

Produces two signals per instrument per timeframe:
  1. alpha_quality  (0..1) — "How good is this setup?"
  2. alpha_direction (-1..+1) — "Which way should we trade?"

Architecture:
  - LiquidityScore  (Structure)  — Proximity to key liquidity levels
  - FairValueScore  (Reversion)  — Deviation from statistical fair value
  - VolatilityScore              — Current vs. average volatility regime
  - MomentumScore                — Fast/slow EMA separation

All factor weights and blending coefficients are loaded from configuration
to allow rapid experimentation without code changes.

NOTE: This is the public/demo version. The production system uses
calibrated parameters derived from live trading data.
"""

import pandas as pd
import pandas_ta as ta
import numpy as np


# ─────────────────────────────────────────────
# FEATURE EXTRACTORS
# ─────────────────────────────────────────────

class LiquidityScore:
    """Structure factor: measures proximity to recent swing highs/lows.
    
    When price sweeps a key level (score → 1.0), there is high probability
    of reversal — a concept from Smart Money / ICT methodology.
    """

    def __init__(self, lookback: int = 20, proximity_threshold: float = 0.5):
        self.lookback = lookback
        self.threshold = proximity_threshold

    def calculate(self, df: pd.DataFrame, atr_series: pd.Series):
        recent_low = df["low"].shift(1).rolling(self.lookback).min()
        recent_high = df["high"].shift(1).rolling(self.lookback).max()

        dist_low = (df["low"] - recent_low) / atr_series
        dist_high = (recent_high - df["high"]) / atr_series

        score_low = np.where(
            dist_low <= 0, 1.0,
            np.where(dist_low <= self.threshold, 1.0 - (dist_low / self.threshold), 0.0),
        )
        score_high = np.where(
            dist_high <= 0, 1.0,
            np.where(dist_high <= self.threshold, 1.0 - (dist_high / self.threshold), 0.0),
        )

        return (
            np.maximum(score_low, score_high),
            np.where(score_low > score_high, "SUPPORT_LOW", "RESISTANCE_HIGH"),
        )


class FairValueScore:
    """Reversion factor: measures deviation from EMA fair value in ATR units.
    
    Returns:
        score (0..1): magnitude of extension from mean
        z_raw (float): signed distance — positive = above fair value
    """

    def __init__(self, ema_period: int = 50):
        self.ema_period = ema_period

    def calculate(self, close_series: pd.Series, atr_series: pd.Series):
        fair_value = ta.ema(close_series, length=self.ema_period)
        if fair_value is None:
            zeros = np.zeros_like(close_series)
            return (
                pd.Series(zeros, index=getattr(close_series, "index", None)),
                pd.Series(zeros, index=getattr(close_series, "index", None)),
            )

        z_raw = (close_series - fair_value) / atr_series
        # Clip at configurable z-threshold (default 2.5 ATR = extreme)
        score = np.clip(abs(z_raw) / 2.5, 0.0, 1.0)
        return score, z_raw


class VolatilityScore:
    """Volatility regime detector: current ATR / rolling average ATR.
    
    Low score → dead market (spread > opportunity)
    High score → active market (favorable for entries)
    """

    def __init__(self, avg_period: int = 50):
        self.period = avg_period

    def calculate(self, atr_series: pd.Series):
        atr_avg = atr_series.rolling(self.period).mean()
        ratio = atr_series / atr_avg
        return np.clip(ratio, 0.0, 1.0)


class MomentumScore:
    """Momentum factor: fast/slow EMA crossover with magnitude.
    
    Returns:
        strength (0..1): magnitude of EMA separation
        direction (-1/0/+1): sign of momentum
        gap_signed (float): raw (fast - slow) / close
    """

    def __init__(self, fast: int = 9, slow: int = 21):
        self.fast = fast
        self.slow = slow

    def calculate(self, close_series: pd.Series):
        fast_ema = ta.ema(close_series, length=self.fast)
        slow_ema = ta.ema(close_series, length=self.slow)
        if fast_ema is None or slow_ema is None:
            zeros = np.zeros_like(close_series)
            z = pd.Series(zeros, index=getattr(close_series, "index", None))
            return z, z, z

        gap_signed = (fast_ema - slow_ema) / close_series
        strength = np.clip(abs(gap_signed) * 1000, 0, 1.0)
        direction = np.sign(gap_signed).replace({np.nan: 0.0})
        return strength, direction, gap_signed


# ─────────────────────────────────────────────
# ALPHA STACK — Weighted Factor Aggregation
# ─────────────────────────────────────────────

class AlphaStack:
    """Combines individual factor scores into a single alpha quality signal.
    
    Weights are configurable and can be tuned per-instrument or per-regime.
    The production system uses calibrated weights; defaults shown here are
    illustrative of the methodology.
    """

    # Default weights (production values differ)
    DEFAULT_WEIGHTS = {
        "structure": 0.35,
        "reversion": 0.30,
        "volatility": 0.20,
        "momentum": 0.15,
    }

    def __init__(self, weights: dict = None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    def get_total_alpha(self, s: float, r: float, v: float, m: float) -> float:
        alpha = (
            self.weights["structure"] * s
            + self.weights["reversion"] * r
            + self.weights["volatility"] * v
            + self.weights["momentum"] * m
        )
        return float(np.clip(alpha, 0.0, 1.0))


# ─────────────────────────────────────────────
# MAIN ALPHA MODEL
# ─────────────────────────────────────────────

class AlphaModel:
    """Orchestrates multi-timeframe alpha computation.
    
    For each instrument, processes M5 (execution), H1, H4, D1 (context)
    timeframes and produces a unified alpha packet with quality score,
    directional bias, and macro trend alignment.
    """

    def __init__(self):
        self.liq = LiquidityScore()
        self.fv = FairValueScore()
        self.vol = VolatilityScore()
        self.mom = MomentumScore()
        self.stack = AlphaStack()

    def _process_tf(self, candles: list) -> dict:
        """Process a single timeframe's candles into alpha signals."""
        df = pd.DataFrame(candles)
        df["time"] = pd.to_datetime(df["time"], unit="s")

        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["atr"] = atr
        df["ema_50"] = ta.ema(df["close"], length=50)

        # Compute all factors
        s_score, s_type = self.liq.calculate(df, atr)
        r_score, z_raw = self.fv.calculate(df["close"], atr)
        v_score = self.vol.calculate(atr)
        m_strength, m_dir, m_gap_signed = self.mom.calculate(df["close"])

        # Extract latest values
        last_s = s_score[-1] if isinstance(s_score, np.ndarray) else s_score.iloc[-1]
        last_r = r_score.iloc[-1]
        last_v = v_score.iloc[-1]
        last_m = m_strength.iloc[-1]
        struct_type = s_type[-1] if isinstance(s_type, np.ndarray) else s_type.iloc[-1]

        total_alpha = self.stack.get_total_alpha(last_s, last_r, last_v, last_m)

        # Trend direction from EMA
        last = df.iloc[-1]
        trend = "NEUTRAL"
        if last["close"] > last["ema_50"]:
            trend = "BULLISH"
        elif last["close"] < last["ema_50"]:
            trend = "BEARISH"

        # Directional features for downstream constraint enforcement
        last_z = float(z_raw.iloc[-1]) if hasattr(z_raw, "iloc") else float(z_raw[-1])
        last_mdir = float(m_dir.iloc[-1]) if hasattr(m_dir, "iloc") else float(m_dir[-1])

        trend_sign = 1.0 if trend == "BULLISH" else (-1.0 if trend == "BEARISH" else 0.0)
        structure_bias = (
            1.0 if "SUPPORT" in str(struct_type).upper()
            else (-1.0 if "RESISTANCE" in str(struct_type).upper() else 0.0)
        )
        reversion_bias = -float(np.sign(last_z)) if abs(last_z) > 0 else 0.0

        # Composite directional signal (blending coefficients are configurable)
        direction = float(np.clip(
            0.45 * trend_sign + 0.30 * last_mdir + 0.15 * structure_bias + 0.10 * reversion_bias,
            -1.0, 1.0,
        ))

        return {
            "alpha": round(float(total_alpha), 2),
            "direction": round(direction, 3),
            "trend": trend,
            "breakdown": {
                "structure": round(float(last_s), 2),
                "reversion": round(float(last_r), 2),
                "volatility": round(float(last_v), 2),
                "momentum": round(float(last_m), 2),
                "structure_type": struct_type,
            },
        }

    def get_market_state(self, data_bundle: dict) -> dict:
        """Process all timeframes and return unified alpha packet."""
        m5_alpha = self._process_tf(data_bundle["M5"])

        # Optional ultra-micro timing confirmation
        m1_alpha = None
        if "M1" in data_bundle:
            try:
                m1_alpha = self._process_tf(data_bundle["M1"])
            except Exception:
                m1_alpha = None

        # Macro context timeframes
        d1_alpha = self._process_tf(data_bundle["D1"])
        h4_alpha = self._process_tf(data_bundle["H4"])
        h1_alpha = self._process_tf(data_bundle["H1"])

        # Status classification
        status = "WAIT"
        if m5_alpha["alpha"] > 0.60:
            status = "REVIEW_REQUIRED"
        if m5_alpha["alpha"] > 0.85:
            status = "HIGH_CONVICTION"

        return {
            "packet_type": "PROBABILISTIC_ALPHA",
            "timestamp": pd.Timestamp.now().isoformat(),
            "alpha_quality": m5_alpha["alpha"],
            "alpha_direction": m5_alpha.get("direction", 0.0),
            "status": status,
            "m5_metrics": m5_alpha,
            "m1_metrics": m1_alpha,
            "macro": {
                "d1_trend": d1_alpha["trend"],
                "h4_trend": h4_alpha["trend"],
                "h1_trend": h1_alpha["trend"],
            },
        }
