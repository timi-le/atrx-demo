# Risk Management Framework

## Overview

ATRX employs a three-layer risk management architecture designed for prop firm compliance while maintaining edge exploitation capability.

## Layer 1: Anti-Martingale Position Sizing

The base risk engine implements the opposite of martingale: it **reduces** position sizes as losses accumulate.

### Drawdown Tiers

| Current DD | Risk Multiplier | Effective Risk (0.50% base) |
|------------|----------------|----------------------------|
| 0 – 1%    | 100%           | 0.50%                      |
| 1 – 2%    | 75%            | 0.375%                     |
| 2 – 3%    | 50%            | 0.25%                      |
| 3%+       | 25%            | 0.125%                     |

### Mathematical Justification

With a 40% win rate and 1.5:1 reward-to-risk, the expected value per trade is:

```
E[PnL] = (0.40 × 1.5R) - (0.60 × 1.0R) = +0.00R (breakeven before edge)
```

The actual edge comes from selective entry (alpha filtering increases effective win rate to ~48-52% on high-conviction trades). Anti-martingale sizing ensures that even during expected drawdowns, the system has capital remaining to exploit the statistical edge when it reasserts.

## Layer 2: Prop Firm Compliance

### Phase-Aware Risk Bounds

| Phase        | DD Type  | Daily DD | Total DD | Risk/Trade    |
|-------------|----------|----------|----------|---------------|
| Challenge   | Static   | 3.8%     | 8.0%     | 0.50 – 1.25%  |
| Verification| Static   | 3.8%     | 8.0%     | 0.25 – 0.75%  |
| Funded      | Trailing | 3.8%     | 8.0%     | 0.25 – 1.00%  |

### Correlation Exposure Tracking

The system maps each symbol to its underlying currency components and tracks net exposure:

```
Position: Long EURUSD  → EUR: +1.0, USD: -1.0
Position: Long GBPUSD  → GBP: +1.0, USD: -1.0
                          ─────────────────────
Net exposure:              EUR: +1.0
                           GBP: +1.0
                           USD: -2.0  ← FLAGGED if > threshold
```

This prevents the common prop firm failure of accumulating excessive directional exposure through seemingly "diversified" positions.

## Layer 3: Portfolio-Level Controls

- **Daily profit target**: When reached, system banks profits and scales risk down
- **Swing protection**: Positions held > N hours are protected during profit banking (don't close strong swing trades to bank intraday profits)
- **Stop-wave detection**: Multiple consecutive stop-outs trigger automatic position reduction across the portfolio
- **Circuit breakers**: Hard stops at 3.8% daily DD and 8.0% total DD — trading halts completely until next session

## ATR-Based Stop Placement

All stop-losses are calculated from the 14-period ATR, ensuring stops adapt to current volatility:

```
stop_distance = ATR × multiplier
risk_amount = balance × risk_pct × dd_multiplier
position_size = risk_amount / (stop_distance × point_value)
```

This means:
- In high volatility: wider stops, smaller positions
- In low volatility: tighter stops, larger positions
- Result: consistent risk-per-trade regardless of market conditions
