# atrx-demo

Production multi-asset algorithmic trading system. Multi-factor alpha engine, three-tier LLM decision validation, anti-martingale risk management, and prop firm compliance. Live since November 2025 with 600+ executed trades.

_Status: reference · Last updated: 2026-05-13_

---

## Quick start

```bash
git clone https://github.com/timi-le/atrx-demo.git
cd atrx-demo
pip install -r requirements.txt
python src/main.py --help
```

Running against live capital requires broker credentials, the C# execution bridge, and the MT5 Expert Advisor configured per the deployment guide in `docs/`.

## What this is

A fully autonomous trading system that runs 24/7 across 15+ instruments in FX, commodities, and crypto. It combines a multi-factor quantitative alpha engine with a three-tier LLM decision layer (Google Gemini) and a risk framework built to institutional and prop-firm standards. Live since November 2025 with 600+ executed trades.

This is not a backtesting framework or a strategy library. The system places real orders against real capital. This repository documents the architecture, the component design, and the proprietary risk and decision logic at the framework level. Specific thresholds, calibration parameters, and the live operational tooling stay private.

## Architecture

```
+---------------------------------------------------------------------+
|                        ATRX trading system                          |
+---------------------------------------------------------------------+
|                                                                     |
|  +---------------+    +---------------+    +---------------------+  |
|  |  Market data  |--->|  Alpha engine |--->|  Candidate ranking  |  |
|  |  (MT5 API)    |    |  (4 factor)   |    |  (multi-timeframe)  |  |
|  +---------------+    +---------------+    +----------+----------+  |
|                                                       |             |
|                                           +-----------v----------+  |
|                                           |   Gemini AI layer    |  |
|                                           |                      |  |
|                                           |  Tier 1: pre-filter  |  |
|                                           |  (Flash, quick gate) |  |
|                                           |                      |  |
|                                           |  Tier 2: entry       |  |
|                                           |  (Pro, full analysis)|  |
|                                           |                      |  |
|                                           |  Tier 3: PM confirm  |  |
|                                           |  (Pro, portfolio)    |  |
|                                           +-----------+----------+  |
|                                                       |             |
|  +---------------+    +---------------+    +-----------v---------+  |
|  |  Portfolio    |<-->|     Risk      |<-->|     Execution       |  |
|  |  manager      |    |    manager    |    |  (C# bridge, MT5)   |  |
|  +---------------+    +---------------+    +---------------------+  |
|                                                                     |
|  +---------------+    +---------------+    +---------------------+  |
|  |   Telegram    |    |   Dashboard   |    |  Decision logger    |  |
|  |   control bot |    |   (Next.js)   |    |  and trade journal  |  |
|  +---------------+    +---------------+    +---------------------+  |
|                                                                     |
+---------------------------------------------------------------------+

  Instruments: XAUUSD, GBPUSD, USDJPY, EURUSD, BTCUSD plus 10 others
  Timeframes:  D1, H4, H1, M15, M5, M1
  Execution:   24/7 automated via MetaTrader 5
```

## Components

### Alpha engine

Multi-factor scoring model in `src/modules/market_data.py`. Produces a quality score on `[0, 1]` and a directional signal on `[-1, +1]`.

| Factor | Weight | What it measures |
|---|---|---|
| Structure | 35% | Proximity to liquidity levels (support/resistance sweeps) |
| Reversion | 30% | Mean-reversion opportunity (deviation from fair value via EMA/ATR z-score) |
| Volatility | 20% | Current ATR vs. rolling average. Regime detection. |
| Momentum | 15% | Fast/slow EMA separation. Trend strength and direction. |

The directional opinion is a blend of trend bias (45%), momentum direction (30%), structure bias (15%), and reversion bias (10%). The result constrains all downstream decisions.

This public repository shows the framework and the architecture. Specific thresholds, calibration parameters, and proprietary enhancements used in the live system are not included.

### Three-tier LLM decision layer

The Gemini API is used as a validation and reasoning layer on top of the quantitative signal, not as a generator of signals.

```
Candidate pool (alpha > threshold)
        |
        v
   +---------+
   | Tier 1  |   Gemini Flash. "Is this worth analyzing?"
   |Pre-filt |   ~$0.001 per call, sub-second.
   +----+----+
        | worthy=true
        v
   +---------+
   | Tier 2  |   Gemini Pro. Full entry decision (BUY/SELL/HOLD).
   | Entry   |   Inputs: alpha scores, macro context, news overlay.
   +----+----+   Constraint: must align with alpha_direction.
        | action=BUY/SELL
        v
   +---------+
   | Tier 3  |   Gemini Pro. Portfolio-level confirmation.
   | PM gate |   Reviews: correlation risk, open exposure, drawdown.
   +---------+   Can: approve, reduce size, or veto.
```

Directional constraint enforcement: the model is never allowed to contradict the alpha direction. If the alpha stack says the bias is bullish, the model cannot recommend a SELL. This rules out the failure mode where LLMs hallucinate market opinions and override the quantitative edge.

### Risk manager

Anti-martingale position sizing in `src/modules/risk_manager.py`. The system reduces exposure during losing streaks rather than averaging in.

| Account drawdown | Risk multiplier | Behaviour |
|---|---|---|
| 0 to 1% | 100% | Full sizing |
| 1 to 2% | 75% | Early caution |
| 2 to 3% | 50% | Defensive |
| 3% and above | 25% | Survival |

### Prop firm compliance

Phase-aware risk budgeting in `src/modules/prop_firm_risk.py`. Covers Challenge, Verification, Funded, and Scaled phases.

- Challenge: 0.50 to 1.25% per trade.
- Funded: 0.25 to 1.00% per trade.
- Currency-correlation tracking (e.g., EURUSD + GBPUSD share USD exposure).
- Dynamic position limits based on available risk budget.
- Drawdown circuit breakers: daily 3.8%, total 8.0%.
- Profit banking with configurable targets.

### Cross-platform execution bridge

```
Python (alpha engine)  --HTTP POST-->  C# bridge  --File queue-->  MT5 EA (MQL5)
                                            |
                                       Persistent queue
                                       (pending, inflight, done/failed)
```

The bridge exists because Python has no native MT5 socket access on Linux or Docker. The C# service acts as a reliable message queue with lease-based retry.

### Live operations

- Telegram bot for pause/resume, force-close positions, status checks, and risk adjustment from a phone.
- Next.js dashboard for real-time P&L, open positions, alpha scores, and decision logs.
- Structured decision logging. Every entry, exit, skip, and veto is logged with full context.
- Automated trade journal. Per-trade snapshots of entry conditions, alpha state, and model reasoning.

## Quantitative concepts demonstrated

- Factor-based alpha models with weighted aggregation, comparable to Fama-French style decomposition applied to execution timeframes.
- Statistical arbitrage via mean-reversion z-score analysis normalised by ATR.
- Regime detection by volatility-based classification of market conditions.
- Portfolio risk management with correlation-aware exposure limits and drawdown-contingent de-risking.
- Position sizing with Kelly-adjacent risk budgeting under institutional constraints.
- Multi-timeframe analysis (D1/H4/H1 macro context informing M5/M1 execution).
- LLM-as-validator architecture where the model validates quantitative signals without overriding direction.

## Tech stack

Python 3.10+, Pandas, pandas-ta, NumPy, Google Gemini API (Flash and Pro), Pydantic Settings, MetaTrader 5 API, C# Bridge on .NET 8, MQL5 Expert Advisor, Next.js, TypeScript, Tailwind CSS, Telegram Bot API, Finnhub, ForexFactory, Docker, Docker Compose.

## What this is NOT

- Not a deployable trading bot. The runnable production system, broker credentials, and live calibration are private.
- Not financial advice. The code is published for technical reference.
- Not a backtesting framework. Backtesting and research live in [research-engine](https://github.com/timi-le/research-engine).
- Not benchmarked against external trading systems. Internal benchmarks are tracked privately.

## Repository layout

```
src/
  main.py                     Core trading loop and orchestration
  api_server.py               FastAPI backend for dashboard
  config/
    settings.py               Pydantic configuration (env-driven)
    presets.py                Trading presets (normal, prop, aggressive)
  modules/
    market_data.py            Alpha engine (4-factor model)
    brain.py                  Three-tier Gemini decision engine
    risk_manager.py           Anti-martingale risk framework
    prop_firm_risk.py         Prop firm compliance layer
    portfolio_manager.py      Portfolio-level coordination
    broker.py                 MT5 API wrapper
    session_manager.py        Trading session awareness
    news_manager.py           Economic calendar integration
    macro_confluence.py       Multi-timeframe trend scoring
    notifier.py               Telegram notifications
    listener.py               Telegram command handler
    decision_logger.py        Structured decision logging
    trade_journal.py          Trade snapshot journal
    symbol_weight_tracker.py  Adaptive symbol weighting
    state_exporter.py         Dashboard state export
bridge_csharp/                C# execution bridge (.NET 8)
mt5/
  ATRX_ExecutorEA.mq5         MetaTrader 5 Expert Advisor
dashboard/                    Next.js real-time dashboard
strategy.xml                  Model reasoning instructions
docker-compose.yml            Container orchestration
Dockerfile                    Python service container
requirements.txt              Python dependencies
```

## Related work

- **[atrx-public](https://github.com/timi-le/atrx-public)**. The sanitized public reference for the broader ATRX architecture.
- **[research-engine](https://github.com/timi-le/research-engine)**. Quantitative research and alpha-generation engine. ML training pipelines, regime detection, backtesting framework.
- **[fx-volatility-predictor](https://github.com/timi-le/fx-volatility-predictor)**. FX volatility forecasting with walk-forward validation.

## Disclaimer

This repository is published for technical reference. The live system's alpha parameters and calibration differ from the framework shown here. Past performance does not guarantee future results. Trading involves substantial risk of loss.

## License

MIT. See `LICENSE`.
