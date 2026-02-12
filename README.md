# ATRX — Algorithmic Trading Risk eXecution

> A production-grade, multi-asset algorithmic trading platform combining quantitative alpha generation with AI-powered decision validation. Built for institutional risk standards and prop firm compliance.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![MetaTrader 5](https://img.shields.io/badge/Execution-MetaTrader%205-orange.svg)]()
[![Google Gemini](https://img.shields.io/badge/AI-Google%20Gemini-blueviolet.svg)]()

---

## What is ATRX?

ATRX is a fully autonomous trading system that runs 24/7, scanning 15+ instruments across FX, commodities, and crypto. It combines a **multi-factor quantitative alpha engine** with a **three-tier LLM decision layer** (Google Gemini) and **institutional-grade risk management** — all coordinated through real-time Telegram controls and a live performance dashboard.

**This is not a backtesting framework or a strategy library.** ATRX is a complete, production-deployed trading operation with real capital allocation, real execution, and real risk controls.

### Key Highlights

- **Multi-Factor Alpha Engine** — Four-component scoring model (Structure, Reversion, Volatility, Momentum) with weighted aggregation and directional bias computation
- **Three-Tier AI Decision Architecture** — Gemini Flash pre-filter → Gemini Pro entry analysis → Gemini Pro portfolio-level confirmation. The AI *validates* quantitative signals — it never overrides the alpha direction
- **Anti-Martingale Risk Engine** — Drawdown-tiered position sizing that *reduces* exposure during losing streaks (opposite of martingale). Includes daily/total drawdown circuit breakers, correlation-aware exposure limits, and per-symbol weight tracking
- **Prop Firm Compliance Layer** — Phase-aware risk budgeting (Challenge → Verification → Funded → Scaled) with dynamic position limits, profit banking, and drawdown-triggered de-risking
- **Cross-Platform Execution Bridge** — Python alpha engine → C# execution bridge → MQL5 Expert Advisor, providing broker-agnostic order management with queue-based reliability
- **Live Operations Infrastructure** — Next.js dashboard, Telegram bot for pause/resume/status, structured decision logging, and automated trade journaling

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ATRX TRADING SYSTEM                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐     ┌──────────────────────┐  │
│  │  Market Data  │───▶│ Alpha Engine │───▶│  Candidate Ranking  │  │
│  │  (MT5 API)    │    │  (4-Factor)  │    │  (Multi-Timeframe)   │  │
│  └──────────────┘    └──────────────┘    └──────────┬───────────┘   │
│                                                      │              │
│                                          ┌───────────▼───────────┐  │
│                                          │   GEMINI AI LAYER     │  │
│                                          │                       │  │
│                                          │  Tier 1: Pre-Filter   │  │
│                                          │  (Flash — quick gate) │  │
│                                          │         │             │  │
│                                          │  Tier 2: Entry        │  │
│                                          │  (Pro — full analysis)│  │
│                                          │         │             │  │
│                                          │  Tier 3: PM Confirm   │  │
│                                          │  (Pro — portfolio)    │  │
│                                          └───────────┬───────────┘  │
│                                                      │              │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────▼───────────┐  │
│  │   Portfolio   │◀──▶│    Risk      │◀──▶│     Execution      │  │
│  │   Manager     │    │   Manager    │    │  (C# Bridge → MT5)   │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │ 
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │  Telegram     │    │  Dashboard   │    │  Decision Logger     │  │
│  │  Control Bot  │    │  (Next.js)   │    │  + Trade Journal     │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘   │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│  Instruments: XAUUSD, GBPUSD, USDJPY, EURUSD, BTCUSD + 10 more      │
│  Timeframes:  D1, H4, H1, M15, M5, M1                               │
│  Execution:   24/7 automated via MetaTrader 5                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Alpha Generation Engine (`src/modules/market_data.py`)

A multi-factor scoring model that produces both a **quality score** (0–1, "how good is this setup?") and a **directional signal** (-1 to +1, "which way?").

**Factor Stack:**

| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| Structure | 35% | Proximity to liquidity levels (support/resistance sweeps) |
| Reversion | 30% | Mean-reversion opportunity (deviation from fair value via EMA/ATR z-score) |
| Volatility | 20% | Current ATR vs. rolling average — regime detection |
| Momentum | 15% | Fast/slow EMA separation — trend strength and direction |

**Directional Blend:**

The system computes a signed directional opinion by blending trend bias (45%), momentum direction (30%), structure bias (15%), and reversion bias (10%) into a single [-1, +1] signal that constrains all downstream decisions.

> **Note:** This public repository shows the framework and architecture. Specific thresholds, calibration parameters, and proprietary enhancements used in the live system are not included.

### 2. Three-Tier AI Decision Layer (`src/modules/brain.py`)

The most distinctive component of ATRX. Rather than using AI to *generate* trading signals, ATRX uses Google Gemini as a **validation and reasoning layer** on top of quantitative signals.

```
Candidate Pool (Alpha > threshold)
        │
        ▼
   ┌─────────┐
   │ TIER 1  │  Gemini Flash — "Is this worth analyzing?"
   │ Pre-Filt│  Cost: ~$0.001/call | Latency: <1s
   └────┬────┘
        │ worthy=true
        ▼
   ┌─────────┐
   │ TIER 2  │  Gemini Pro — Full entry decision (BUY/SELL/HOLD)
   │ Entry   │  Receives: alpha scores, macro context, news overlay
   └────┬────┘  Constraint: MUST align with alpha_direction
        │ action=BUY/SELL
        ▼
   ┌─────────┐
   │ TIER 3  │  Gemini Pro — Portfolio-level confirmation
   │ PM Gate │  Reviews: correlation risk, open exposure, drawdown
   └─────────┘  Can: approve, reduce size, or veto
```

**Key Innovation — Directional Constraint Enforcement:**

The AI is *never* allowed to contradict the quantitative alpha direction. If the alpha stack says the bias is bullish, Gemini cannot recommend a SELL. This prevents the well-known failure mode where LLMs "hallucinate" market opinions that override quantitative edge.

### 3. Risk Management Framework

**Anti-Martingale Position Sizing (`src/modules/risk_manager.py`):**

| Drawdown Level | Risk Multiplier | Philosophy |
|----------------|----------------|------------|
| 0–1% | 100% (full) | Normal operations |
| 1–2% | 75% | Early caution |
| 2–3% | 50% | Defensive mode |
| 3%+ | 25% | Survival mode |

**Prop Firm Risk Layer (`src/modules/prop_firm_risk.py`):**

- Phase-aware budgeting (Challenge: 0.50–1.25% per trade, Funded: 0.25–1.00%)
- Currency correlation tracking (e.g., EURUSD + GBPUSD = shared USD exposure)
- Dynamic position limits based on available risk budget
- Drawdown circuit breakers (daily 3.8%, total 8.0%)
- Profit banking with configurable targets

### 4. Cross-Platform Execution Bridge

```
Python (Alpha Engine)  ──HTTP POST──▶  C# Bridge  ──File Queue──▶  MT5 EA (MQL5)
                                         │
                                    Persistent queue
                                    (pending → inflight → done/failed)
```

The execution bridge solves the problem of Python not having native MT5 socket access on Linux/Docker deployments. The C# bridge acts as a reliable message queue with lease-based retry logic.

### 5. Live Operations

- **Telegram Bot**: Pause/resume trading, force close positions, check status, adjust risk — all from your phone
- **Next.js Dashboard**: Real-time P&L, open positions, alpha scores, decision logs
- **Structured Logging**: Every decision (entry, exit, skip, veto) is logged with full context for post-mortem analysis
- **Trade Journal**: Automated snapshots of entry conditions, alpha state, and AI reasoning for each trade

---

## Project Structure

```
atrx/
├── src/
│   ├── main.py                    # Core trading loop and orchestration
│   ├── api_server.py              # FastAPI backend for dashboard
│   ├── config/
│   │   ├── settings.py            # Pydantic configuration (env-driven)
│   │   └── presets.py             # Trading presets (normal/prop/aggressive)
│   └── modules/
│       ├── market_data.py         # Alpha engine (4-factor model)
│       ├── brain.py               # Three-tier Gemini decision engine
│       ├── risk_manager.py        # Anti-martingale risk framework
│       ├── prop_firm_risk.py      # Prop firm compliance layer
│       ├── portfolio_manager.py   # Portfolio-level coordination
│       ├── broker.py              # MT5 API wrapper
│       ├── session_manager.py     # Trading session awareness
│       ├── news_manager.py        # Economic calendar integration
│       ├── macro_confluence.py    # Multi-timeframe trend scoring
│       ├── notifier.py            # Telegram notifications
│       ├── listener.py            # Telegram command handler
│       ├── decision_logger.py     # Structured decision logging
│       ├── trade_journal.py       # Trade snapshot journal
│       ├── symbol_weight_tracker.py # Adaptive symbol weighting
│       └── state_exporter.py      # Dashboard state export
├── bridge_csharp/                 # C# execution bridge
│   └── ExecutionBridge/
│       ├── Program.cs             # HTTP listener + MT5 queue
│       ├── FileQueueStore.cs      # Persistent file-based queue
│       └── Models.cs              # Order/response models
├── mt5/
│   └── ATRX_ExecutorEA.mq5       # MetaTrader 5 Expert Advisor
├── dashboard/                     # Next.js real-time dashboard
│   └── src/
│       ├── components/Dashboard.tsx
│       └── lib/atrx-client.ts
├── strategy.xml                   # AI reasoning instructions
├── docker-compose.yml             # Container orchestration
├── Dockerfile                     # Python service container
└── requirements.txt               # Python dependencies
```

---

## Quantitative Concepts Demonstrated

This system demonstrates practical application of concepts central to quantitative finance:

- **Factor-Based Alpha Models** — Multi-factor scoring with weighted aggregation (comparable to Fama-French style decomposition applied to execution timeframes)
- **Statistical Arbitrage** — Mean-reversion detection via z-score analysis normalized by ATR
- **Regime Detection** — Volatility-based classification of market conditions (trending vs. ranging)
- **Portfolio Risk Management** — Correlation-aware exposure limits, anti-martingale sizing, and drawdown-contingent de-risking
- **Position Sizing Theory** — Kelly-adjacent risk budgeting with institutional constraints
- **Multi-Timeframe Analysis** — Macro context (D1/H4/H1) informing micro execution (M5/M1)
- **AI/ML Integration** — LLM-as-validator architecture that preserves quantitative edge while adding contextual reasoning

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Alpha Engine | Python 3.10+, pandas, pandas-ta, numpy |
| AI Layer | Google Gemini API (Flash + Pro) |
| Configuration | Pydantic Settings, environment-driven |
| Execution | MetaTrader 5 API, C# Bridge (.NET 8), MQL5 EA |
| Dashboard | Next.js, TypeScript, Tailwind CSS |
| Notifications | Telegram Bot API |
| News Data | Finnhub API, ForexFactory calendar |
| Deployment | Docker, Docker Compose |

---

## Disclaimer

This repository is provided for **educational and portfolio purposes**. It demonstrates system architecture, quantitative methodology, and software engineering practices. The alpha generation parameters in the live system differ from what is shown here. Past performance does not guarantee future results. Trading involves substantial risk of loss.

---

## Author

**Timilehin Olapade**

- Tax Planning Specialist at Union Bank PLC
- Quantitative developer
- Algorithmic trading system architect
- Applicant: Master of Quantitative Investment Management, University of New Brunswick

---

## License

MIT License — See [LICENSE](LICENSE) for details.
