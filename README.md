# Bollinger Bands Options Trading Dashboard PRO

A real-time, high-probability options buying and scanning platform for Indian derivatives markets (NSE / BSE) built on **Dhan HQ APIs**. Engineered specifically for **Option Buyers** to capture high-velocity, high-gamma directional moves while strictly avoiding time-decay ($\Theta$) consolidation traps.

---

## 📑 Table of Contents
1. [Architecture Overview](#-architecture-overview)
2. [🔒 Zero-Token Security Policy](#-zero-token-security-policy)
3. [🚀 The 4 Core Strategy Setups (CE & PE)](#-the-4-core-strategy-setups-ce--pe)
4. [⏱️ Execution Timeframes & Universe](#️-execution-timeframes--universe)
5. [🎯 Dual Spot & Option Premium Engine](#-dual-spot--option-premium-engine)
6. [📈 Forward-Testing & Paper Trading Journal](#-forward-testing--paper-trading-journal)
7. [🔌 REST API & SSE Live Streams](#-rest-api--sse-live-streams)
8. [🛠️ Quick Start & Verification](#️-quick-start--verification)

---

## 🏛 Architecture Overview

```
                      ┌──────────────────────────────────────────────┐
                      │              React + Vite + Tailwind         │
                      │         (Port 5174 - Dark Financial UI)      │
                      └───────┬──────────────────────────────▲───────┘
                              │ HTTP Requests                │ Server-Sent Events (SSE)
                              │ (Headers: X-Dhan-*)          │ /api/signals/stream
                              ▼                              │
                      ┌──────────────────────────────────────┴───────┐
                      │                 FastAPI Backend              │
                      │            (Port 8001 - Async Workers)       │
                      └───────┬──────────────────────────────▲───────┘
                              │ Scan Tasks                   │ Feed / Calculations
                              ▼                              │
        ┌────────────────────────────────────┐ ┌─────────────┴──────────────────────┐
        │        Strategy & Math Engine      │ │       Dhan HQ Live / Demo Feed     │
        │  • Technical Indicators (TA-Lib)   │ │  • Intraday OHLCV Candles          │
        │  • Setups 1, 2, 3, 4 Evaluation    │ │  • Rate Limiting (5 req/s)         │
        │  • Strike Selector (Delta ~0.55)   │ │  • Fallback Simulated Wave Mode    │
        │  • Paper Trading Journal Engine    │ │  • Redacting Security Filter       │
        └────────────────────────────────────┘ └────────────────────────────────────┘
```

- **Backend**: Python 3.10+ / FastAPI asynchronous server utilizing an event-driven `ScannerWorker` background service. Provides automatic Dhan API rate limiting with retry backoff, dynamic candle synthesis, and SSE event broadcast.
- **Frontend**: React 18, TypeScript, Tailwind CSS, and Lucide icons. Features a responsive dark interface, top Navigation with live connection status, an Index Hero Radar, setup-filtered Signal Cards, and an interactive Paper Portfolio modal with live P&L tracking.
- **Data Flow**: The backend scanner polls index and equity intraday candles every 10–30 seconds. On each cycle, technical indicators and strategy rules are evaluated; new signals trigger automated paper positions (if enabled), and snapshots are broadcast via SSE to connected frontend clients.

---

## 🔒 Zero-Token Security Policy

Your Dhan Client ID and 24-hour Access Token are **never stored anywhere permanently**:
- **Never saved to `.env`, configuration files, SQLite, or databases.**
- **Never committed to Git or written to persistent disk.**
- **Stored exclusively in browser `sessionStorage`**: Tokens remain in volatile browser memory only for the duration of the active browser tab.
- **In-Memory Request Transmission**: Transmitted via HTTP headers `X-Dhan-Client-Id` and `X-Dhan-Access-Token` over localhost/HTTPS.
- **Process-Wide Security Log Redaction**: Dedicated `RedactingFilter` and custom `LogRecordFactory` hook mask all JWT tokens (`eyJ...`) and raw credentials from server logs and console outputs.
- **One-Click Disconnect**: Instantly clears `sessionStorage` and returns the application to Simulated Demo Mode.

---

## 🚀 The 4 Core Strategy Setups (CE & PE)

The dashboard continuously evaluates four high-probability option buying setups designed to enter momentum before volatility expands:

### 1. Setup 1: Volatility Squeeze & Expansion Breakout *(CE & PE)*
- **Objective**: Catch explosive directional breakouts immediately following extreme price coiling.
- **Technical Conditions**:
  - **Coil**: Bollinger BandWidth ($\frac{\text{Upper} - \text{Lower}}{\text{Middle}} \times 100$) reaches its 20-period minimum or an absolute squeeze threshold ($\le 5\%$).
  - **Breakout**: Candle closes decisively outside the Upper Band (CE) or Lower Band (PE).
  - **Volume & VWAP**: Volume surge $> 1.2\times$ 20-period average volume, with price closing above Session VWAP (CE) or below Session VWAP (PE).
  - **Momentum Filter**: Wilder's RSI(14) $> 60$ for Call options, or $< 40$ for Put options.
- **Stop-Loss**: Placed at the 20-period Bollinger Middle Band (20 SMA).

### 2. Setup 2: "Walking the Bands" with 9 EMA *(CE & PE)*
- **Objective**: Ride strong runaway intraday trends without premature exit during 150–300+ point index moves.
- **Technical Conditions**:
  - **Trend Strength**: Strong directional regime indicated by $\text{ADX}(14) > 25$.
  - **Band Walking**: Multiple prior candles pressing or closing outside the Upper Band (CE) or Lower Band (PE).
  - **Pullback & Trigger**: Price pulls back shallowly toward the 9-period EMA without breaking the 20 SMA, then prints a bounce candle confirming continuation.
- **Stop-Loss**: Dynamically anchored to the 9-period EMA or previous swing low/high.

### 3. Setup 3: Bollinger W-Bottom & M-Top Reversal *(CE & PE)*
- **Objective**: Pinpoint institutional exhaustion reversals with favorable risk-to-reward.
- **Technical Conditions**:
  - **W-Bottom (CE)**:
    1. First swing low closes outside the Lower Bollinger Band.
    2. Price rebounds toward the Middle Band to form the neckline.
    3. Second swing low remains **strictly inside** the Lower Bollinger Band.
    4. **Bullish RSI Divergence**: Second price low is equal or lower than the first, but RSI prints a higher trough.
    5. Trigger: Price crosses above the intermediate neckline resistance.
  - **M-Top (PE)**:
    1. First swing high closes outside the Upper Bollinger Band.
    2. Price pulls back toward the Middle Band to form the neckline.
    3. Second swing high remains **strictly inside** the Upper Bollinger Band.
    4. **Bearish RSI Divergence**: Second price high is equal or higher than the first, but RSI prints a lower peak.
    5. Trigger: Price crosses below the intermediate neckline support.
- **Stop-Loss**: Placed just beyond the second pivot extreme.

### 4. Setup 4: 9:30 AM Opening Range Breakout (ORB) *(CE & PE)*
- **Objective**: Exploit high opening volatility between 09:30 AM and 10:30 AM IST.
- **Technical Conditions**:
  - **Opening Window**: Establishes the 15-minute Opening Range High and Low (09:15–09:30 AM IST).
  - **Breakout Confirmation**: First candle after 09:30 AM breaking above OR High (CE) or below OR Low (PE).
  - **Bollinger Expansion**: BandWidth expands with price aligned with Session VWAP.
- **Stop-Loss**: Opposite boundary of the opening candle or Session VWAP.

---

## ⏱️ Execution Timeframes & Universe

| Instrument Universe | Primary Execution Timeframe | Setup 4 (ORB) Timeframe |
| :--- | :--- | :--- |
| **Benchmark Indices** *(NIFTY 50, BANKNIFTY, FINNIFTY, SENSEX, MIDCPNIFTY)* | **5-Minute** | **3-Minute / 5-Minute** |
| **Liquid F&O Momentum Stocks** *(~30 Curated Equities)* | **15-Minute** | **5-Minute** |

### Curated High-Beta Universe:
- **Indices**: NIFTY 50, BANKNIFTY, FINNIFTY, SENSEX, MIDCPNIFTY.
- **Banking & Financials**: HDFCBANK, ICICIBANK, SBIN, AXISBANK, KOTAKBANK, BAJFINANCE, BAJAJFINSV.
- **IT & Tech**: RELIANCE, TCS, INFY, HCLTECH, TECHM, WIPRO.
- **Auto & Industrials**: TATAMOTORS, MARUTI, M&M, BAJAJ-AUTO, EICHERMOT, LT.
- **Metals & Energy**: TATASTEEL, JSWSTEEL, HINDALCO, COALINDIA, ONGC, NTPC.
- **FMCG & Pharma**: ITC, TITAN, SUNPHARMA, CIPLA, DRREDDY, BHARTIARTL, TRENT, BEL, ADANIENT, ADANIPORTS.

---

## 🎯 Dual Spot & Option Premium Engine

For every active signal, the engine calculates both underlying spot parameters and corresponding option contract premium levels:

### 1. Underlying Spot Calculation
- **Entry Price**: Trigger candle close.
- **Stop-Loss**: Setup-specific structural level (Middle Band, 9 EMA, or pattern pivot).
- **Mathematical SL Guarantee**:
  - CE SL is strictly verified to be $< \text{Entry}$.
  - PE SL is strictly verified to be $> \text{Entry}$.
  - Minimum risk cushion enforced ($\ge 2.0$ points or $0.25\times$ strike step).
- **Target 1**: $1:1.5$ Risk-to-Reward ($\text{Entry} \pm 1.5 \times \text{Risk}$).
- **Target 2**: $1:2.5$ Risk-to-Reward ($\text{Entry} \pm 2.5 \times \text{Risk}$).

### 2. 1-Strike ITM Option Selection ($\Delta \approx 0.55$)
Option buyers maximize gamma acceleration while minimizing theta decay by trading **1-strike In-The-Money (ITM)**:
- **Call (CE)**: $\text{Recommended Strike} = \text{ATM Strike} - \text{Strike Step}$.
- **Put (PE)**: $\text{Recommended Strike} = \text{ATM Strike} + \text{Strike Step}$.

### 3. Estimated Option Premium & Risk Levels
Using an operational delta $\Delta = 0.55$:
$$\text{Option Risk Points} = \min(\text{Spot Risk} \times 0.55, \, \text{Entry Premium} \times 0.70)$$
$$\text{Option Target 1 Points} = \text{Spot Risk} \times 0.55 \times 1.5$$
$$\text{Option Target 2 Points} = \text{Spot Risk} \times 0.55 \times 2.5$$

### 4. Official NSE Lot Sizes
Calculations apply exact NSE lot sizes:
- **NIFTY 50**: 65
- **BANKNIFTY**: 30
- **FINNIFTY**: 65
- **SENSEX**: 20
- **MIDCPNIFTY**: 120
- **Equities**: RELIANCE (500), HDFCBANK (650), ICICIBANK (700), SBIN (750), TATASTEEL (5500), TCS (175), INFY (400), etc.

---

## 📈 Forward-Testing & Paper Trading Journal

The dashboard features a paper trading and forward-testing journal engine:
- **Simulated Demo Feed**: Operates outside market hours or without credentials, allowing risk-free testing of setups, signals, and execution flows.
- **Auto-Trade Toggle**: Automatically opens paper positions whenever new valid signals trigger.
- **Lot Size Management**: Configurable default lots applied to each trade.
- **Dynamic Breakeven SL**: When Target 1 (1:1.5 RR) is achieved, the trade status changes to `TARGET_1` and the stop-loss is automatically trailed to breakeven (`underlying_entry`).
- **Target 2 & Stop-Loss Execution**: Positions are automatically closed when Target 2 or trailing SL is hit, with exit timestamp, reason, and P&L in points and rupees recorded.
- **Live Performance Metrics**: Real-time tracking of Total Realized P&L, Unrealized P&L, Overall Win Rate %, and total/winning/losing trades.

---

## 🔌 REST API & SSE Live Streams

The FastAPI backend exposes the following endpoints under `/api`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Health check, active operating mode (live/demo), and version |
| `POST` | `/api/auth/verify` | Validate 24-hour Dhan credentials against Dhan fund limit APIs |
| `POST` | `/api/auth/disconnect` | Clear session credentials and revert to demo mode |
| `GET` | `/api/universe` | List supported indices, equities, strike steps, and lot sizes |
| `GET` | `/api/signals/snapshot` | Current active signals and market radar status |
| `GET` | `/api/signals/stream` | Server-Sent Events (SSE) live stream for signals and radar |
| `POST` | `/api/signals/scan-now` | Trigger an immediate manual scanning cycle |
| `GET` | `/api/paper/portfolio` | Retrieve active paper positions, trade history, and analytics |
| `POST` | `/api/paper/trade` | Manually open a paper position from a signal |
| `DELETE` | `/api/paper/trade/{trade_id}` | Manually close an open paper position |
| `POST` | `/api/paper/settings` | Update auto-trade toggle and default lot size |
| `POST` | `/api/paper/reset` | Reset paper portfolio, clear active trades and history |

Interactive Swagger documentation is available at [http://localhost:8001/docs](http://localhost:8001/docs).

---

## 🛠️ Quick Start & Verification

### Prerequisites
- **Python**: 3.10+ (Virtual environment with packages in `backend/requirements.txt`)
- **Node.js**: v18+ & **npm**

### 1-Line Unified Launcher
To launch both FastAPI backend (port 8001) and Vite frontend (port 5174) with a single command:

```bash
./run_dashboard.sh
```

The script will automatically:
1. Verify Python virtual environment (`/Users/manigopal/Documents/SSCREENER/venv` or `./venv`).
2. Verify Node.js and npm installations.
3. Cleanly terminate any stale processes holding ports `8001` or `5174`.
4. Launch the FastAPI server and await health check readiness.
5. Launch the Vite frontend dev server.
6. Gracefully stop both services on `Ctrl+C` (SIGINT/SIGTERM).

### Accessing the Applications
- **Web Dashboard**: [http://localhost:5174](http://localhost:5174)
- **Interactive API Docs**: [http://localhost:8001/docs](http://localhost:8001/docs)

### Running Verification Tests

#### Backend Test Suite (Pytest)
```bash
/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v
```

#### Frontend Production Build
```bash
cd frontend && npm run build
```
