# Bollinger Bands Options Trading Dashboard PRO

A real-time, high-probability options buying and scanning platform for Indian derivatives markets (NSE) built on **Dhan HQ APIs**. Designed specifically for **Option Buyers** to capture high-velocity, high-gamma moves while strictly avoiding time-decay ($\Theta$) consolidation traps.

---

## 🔒 Zero Token Persistence Architecture

Your Dhan Client ID and 24-hour Access Token are **never stored anywhere permanently**:
- **Never saved to `.env`, disk, SQLite, or databases.**
- **Never committed to Git.**
- Stored exclusively in browser **`sessionStorage`** and transmitted via secure HTTP headers (`X-Dhan-Client-Id` and `X-Dhan-Access-Token`).
- Automatically redacted from backend logs via dedicated security filters.
- Cleared immediately upon closing the browser tab.

---

## 🚀 The Four Core Strategy Setups (CE & PE)

The dashboard continuously scans the **4 major benchmark indices** and **~30 curated high-beta liquid F&O momentum stocks** across 4 proven Bollinger Band setups:

### 1. Setup 1: Volatility Squeeze & Expansion Breakout *(CE & PE)*
- **Objective**: Catch explosive breakout moves directly out of low-volatility coiling.
- **Rules**: BandWidth contracts to 20-period low $\rightarrow$ Candle closes decisively outside Upper/Lower band $\rightarrow$ Volume surge $+$ Price confirms above/below Session VWAP $\rightarrow$ Wilder's RSI(14) $> 60$ (for CE) or $< 40$ (for PE).

### 2. Setup 3: Bollinger W-Bottom & M-Top Reversal *(CE & PE)*
- **Objective**: Early high-reward reversal entries at institutional exhaustion points.
- **Rules**: 
  - **W-Bottom (CE)**: First low closes outside lower band; second low stays strictly inside lower band with **Bullish RSI Divergence**; triggers upon breaking the neckline high.
  - **M-Top (PE)**: First high closes outside upper band; second high stays strictly inside upper band with **Bearish RSI Divergence**; triggers upon breaking the neckline low.

### 3. Setup 2: "Walking the Bands" with 9 EMA *(CE & PE)*
- **Objective**: Trend surfing without premature exit during 150–250+ point index runs.
- **Rules**: Multi-candle trend riding outside Upper/Lower band with $\text{ADX} > 25$; triggers on a shallow pullback and bounce/rejection at the $9\text{ EMA}$. Stop-loss trailed dynamically at the $9\text{ EMA}$.

### 4. Setup 4: 9:30 AM Opening Range Breakout (ORB) *(CE & PE)*
- **Objective**: Fast morning velocity setup active between 09:30 AM and 10:30 AM IST.
- **Rules**: Initial 15m opening range (09:15–09:30 AM) high/low breached simultaneously with Bollinger Band flaring and VWAP bias.

---

## ⏱️ Execution Timeframes

| Instrument Universe | Primary Execution Timeframe | Setup 4 (ORB) Timeframe |
| :--- | :--- | :--- |
| **Benchmark Indices** *(NIFTY 50, BANKNIFTY, FINNIFTY, SENSEX)* | **5-Minute** | **3-Minute / 5-Minute** |
| **Momentum Stocks** *(Reliance, HDFC Bank, ICICI Bank, SBIN, etc.)* | **15-Minute** | **5-Minute** |

---

## 🎯 Strike Recommendation & Risk Management Engine

For every active signal, the engine automatically calculates:
- **Recommended Option Strike**: 1-Strike ITM ($\Delta \approx 0.55 - 0.60$) or ATM to balance delta responsiveness against theta decay.
- **Stop-Loss (SL)**: Dynamically calculated based on the 20 SMA (Middle Band), 9 EMA, or pattern pivot.
- **Target 1**: $1:1.5$ Risk-to-Reward (partial profit taking & move SL to breakeven).
- **Target 2**: $1:2.5$ Risk-to-Reward (runner target).

---

## 🛠️ Quick Start

### 1-Line Launcher
```bash
./run_dashboard.sh
```

- **Frontend Dashboard:** [http://localhost:5174](http://localhost:5174)
- **FastAPI Documentation:** [http://localhost:8001/docs](http://localhost:8001/docs)

### Forward-Testing & Simulated Feed
Outside market hours or before entering your Dhan credentials, the engine automatically operates in **Simulated Demo Mode**, generating realistic live price waves and setups so you can forward-test and inspect the UI at any time.

When ready for live trading, click **"Enter 24h Dhan Token"** in the top navigation bar to seamlessly switch into the **Live Market Feed**.
