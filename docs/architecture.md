# ATRX System Architecture

## Design Philosophy

ATRX follows a **"quantitative alpha + AI validation"** architecture. The core principle is that quantitative signals generate edge, while AI provides contextual reasoning and risk-aware filtering. The AI layer can only *agree* or *abstain* — it can never contradict the quantitative direction.

This architecture avoids the common failure mode of LLM-based trading: hallucinated market opinions overriding systematic edge.

## Data Flow

```
1. Market Data Collection (MT5 API)
   └── Multi-timeframe candles: D1, H4, H1, M15, M5, M1
       └── For each of 15+ instruments simultaneously

2. Alpha Computation (AlphaModel)
   ├── Per-timeframe factor scoring
   │   ├── Structure (liquidity level proximity)
   │   ├── Reversion (fair value deviation)
   │   ├── Volatility (regime detection)
   │   └── Momentum (trend strength)
   ├── Weighted aggregation → alpha_quality (0..1)
   └── Directional blending → alpha_direction (-1..+1)

3. Candidate Ranking (Main Loop)
   ├── Filter: alpha_quality > threshold
   ├── Rank by: quality × effective_symbol_weight
   └── Select top K candidates per cycle

4. AI Validation (GeminiBrain)
   ├── Tier 1: Pre-filter (Flash) — "Worth analyzing?"
   ├── Tier 2: Entry (Pro) — "BUY/SELL/HOLD + sizing"
   │   └── CONSTRAINT: must align with alpha_direction
   └── Tier 3: PM (Pro) — "Portfolio-level approve/veto"

5. Risk Management Pipeline
   ├── Anti-martingale position sizing
   ├── Correlation exposure check
   ├── Prop firm budget validation
   └── Circuit breaker check (daily/total DD)

6. Execution
   ├── Python → HTTP POST → C# Bridge
   ├── C# Bridge → File Queue → MT5 EA
   └── Confirmation → Telegram notification
```

## Component Interaction

### Trading Cycle (runs every 30s)

Each cycle:
1. Update equity from MT5
2. Check circuit breakers (halt if DD limits hit)
3. Check trading session (London/NY only)
4. Scan for closed trades (update symbol weights)
5. Manage open positions (profit banking, trailing)
6. Fetch multi-TF data for each symbol
7. Compute alpha → rank candidates
8. For top candidates: Tier 1 → Tier 2 → Tier 3 → Execute
9. Export state to dashboard
10. Log all decisions

### Symbol Weight Tracking

Adaptive symbol allocation based on recent performance:
- Winning symbols get higher weight (more opportunities)
- Losing symbols get reduced weight (fewer opportunities)  
- Weights bounded [0.3, 2.0] to prevent complete exclusion
- Reset mechanism after extended periods

### Profit Banking

When daily P&L reaches target:
1. Identify positions to close (weakest first)
2. Protect swing trades (held > N hours)
3. Close enough to bank the target
4. Scale remaining risk by POST_TARGET_RISK_MULTIPLIER

## Cross-Platform Execution

The execution bridge solves a specific engineering challenge: the Python alpha engine runs on Linux/Docker, but MetaTrader 5's native API only works on Windows.

Solution: A C# HTTP bridge that translates order requests into file-based queues consumed by an MQL5 Expert Advisor.

```
Python                    C#                       MT5
──────                    ──                       ───
POST /order ──────────▶  Parse JSON
                          Write to queue/pending/
                                                    EA polls pending/
                                                    Move to inflight/
                                                    Execute order
                                                    Write to done/ or failed/
              ◀────────  Return confirmation
```

Queue states: pending → inflight (leased) → done | failed

This provides:
- Reliability (persistent file queue survives restarts)
- Auditability (every order has a file trail)
- Decoupling (Python doesn't need Windows)
