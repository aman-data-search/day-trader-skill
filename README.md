# US100 M5 Intraday Decision Support Skill

An analytical, zero-execution decision support skill for **US100 / NAS100** (proxied via `QQQ`) on the **5-minute (M5)** timeframe. Designed to run as an automated, scheduled skill inside **Meta Muse** or as a standalone CLI tool, providing structured technical trade cards for manual execution on MetaTrader 5 (MT5).

All automated broker routing, order entry scripts, and position-sizing modules have been decoupled. The system operates strictly as a deterministic signal generator and statistical audit engine.

---

## Strategy & Quantitative Rules

* **Asset Reference**: US100 / NAS100 (tracked via liquid proxy `QQQ`).
* **Timeframe**: 5-minute (M5) candle closes.
* **Opening Range Window**: 09:30 AM to 09:45 AM Eastern Time (first 3 completed M5 candles: $B_1, B_2, B_3$).
* **Opening Range High ($\text{ORB}_{\text{High}}$)**: $\max(\text{High}_{B1}, \text{High}_{B2}, \text{High}_{B3})$
* **Opening Range Low ($\text{ORB}_{\text{Low}}$)**: $\min(\text{Low}_{B1}, \text{Low}_{B2}, \text{Low}_{B3})$
* **Structural Stop-Loss ($\text{SL}_{\text{midpoint}}$)**: 
  $$\text{SL}_{\text{midpoint}} = \frac{\text{ORB}_{\text{High}} + \text{ORB}_{\text{Low}}}{2}$$
* **Breakout Triggers**:
  * **Bullish Breakout (BUY)**: First M5 candle after 09:45 AM ET closing strictly above $\text{ORB}_{\text{High}}$.
  * **Bearish Breakout (SELL)**: First M5 candle after 09:45 AM ET closing strictly below $\text{ORB}_{\text{Low}}$.
* **Risk Geometry ($R$)**:
  $$R = |\text{Entry Close} - \text{SL}_{\text{midpoint}}|$$
* **Take-Profit Target (Strict 1.5R)**:
  * **BUY**: $\text{Take-Profit} = \text{Entry Close} + (1.5 \times R)$
  * **SELL**: $\text{Take-Profit} = \text{Entry Close} - (1.5 \times R)$
* **Empirical Monte Carlo Audit**:
  * Samples from 60 calendar days of historical M5 bars, filtered strictly to **Regular Trading Hours (RTH: 09:30–16:00 ET)**.
  * Replays **10,000 bootstrap simulation paths** across a 30-bar (2.5-hour) holding horizon to measure target vs. stop probability and Expected Value ($\text{EV}$).

---

## Directory Architecture

```
day-trader-skill/
├── .env                     # Alpaca API credentials (git-ignored)
├── .env.example             # Credential template
├── .gitignore               # Security & cache exclusion manifest
├── LICENSE                  # MIT License
├── README.md                # Technical system documentation
├── run_analysis.py          # Master CLI driver & terminal card formatter
├── skill.json               # Meta Muse skill registration & cron schedules
├── trader/
│   ├── config.json          # Strategy parameters & lookback configuration
│   ├── feed.py              # Alpaca Data API v2 (feed=iex) RTH ingestion layer
│   ├── data/                # Cached 60-day RTH historical M5 bars (git-ignored)
│   └── state/               # Ephemeral intraday run artifacts (git-ignored)
├── trader-entry/
│   └── entry.py             # ORB formation & candle close breakout detector
├── trader-exit/
│   └── exit.py              # Midpoint SL and 1.5R TP target calculator
└── trader-timemachine/
    └── timemachine.py       # 10,000-path bootstrap Monte Carlo verification engine
```

---

## Installation & Setup

### 1. Requirements
* Python 3.8 or newer (standard library only; no external package dependencies required).
* Alpaca Markets Free Tier account for market data.

### 2. Configure Credentials
Copy the example environment file and populate your Alpaca keys:
```bash
cp .env.example .env
```
Edit `.env`:
```env
ALPACA_API_KEY=your_actual_key_here
ALPACA_SECRET_KEY=your_actual_secret_here
```

---

## CLI Usage

### 1. Synchronize Historical Cache (Daily at 09:15 AM ET)
Downloads 60 days of completed RTH 5-minute bars via Alpaca's un-delayed `feed=iex` endpoint and stores them in `trader/data/history_m5.json`:
```bash
python run_analysis.py --cache
```

### 2. Active Breakout Scanner (Intraday 09:50–11:30 AM ET)
Evaluates completed M5 session candles. Once a breakout close occurs outside the 09:30–09:45 ET range, it calculates trade geometry and executes a 10,000-path Monte Carlo audit:
```bash
python run_analysis.py --scan
```

---

## Sample Terminal Decision Card

When a valid setup triggers, `run_analysis.py` displays the trade ticket:

```
======================================================================
               US100 INTRADAY DECISION CARD (M5 ORB)                 
======================================================================
  Signal Timestamp    : 2026-11-05 09:45:00 ET
  Direction           : SELL (Bearish Range Expansion)
  Asset Reference     : US100 / NAS100 (Proxy: QQQ)
----------------------------------------------------------------------
  TRADE EXECUTION TARGETS
  Entry Reference     : 669.62
  Stop-Loss Level     : 677.27  [Strict ORB Midpoint]
  Take-Profit Level   : 658.14  [Strict 1.5R Target]
  Risk Distance       : 7.66 Index Points
  Reward Distance     : 11.48 Index Points
----------------------------------------------------------------------
  MONTE CARLO EMPIRICAL AUDIT (10,000 Bootstrap Runs | 60-Day RTH)
  Target Probability  : 0.23% (Hits 1.5R before Midpoint SL)
  Stop Probability    : 2.24%
  Expected Return     : -0.019 R per trade
======================================================================
  Execution Note      : Place order manually on MT5.
  Session Cut-Off     : Close trade manually by 15:55 ET if still active.
======================================================================
```

---

## Meta Muse Integration

The repository includes `skill.json` for registration inside Meta Muse:

| Cron Expression | Action | Function |
| :--- | :--- | :--- |
| `15 9 * * 1-5` | `sync-cache` | Refreshes 60-day RTH M5 historical bars prior to open. |
| `50,55 9,10,11 * * 1-5` | `scan-orb` | Scans completed M5 candles and outputs decision cards. |

---

## Operational Safeguards

* **Manual Execution**: Orders are never placed autonomously. Execution occurs manually via MT5.
* **Intraday Hard Flat**: Any open position must be manually flattened before 15:55 ET to prevent overnight financing charges and gap risk.