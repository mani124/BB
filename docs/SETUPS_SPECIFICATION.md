# Bollinger Bands Options Trading Dashboard PRO
## Complete Trading Setups & Algorithmic Architecture Specification

> **Version:** 1.0.0 PRO  
> **Target Asset Classes:** NSE Benchmark Indices (`NIFTY 50`, `BANK NIFTY`, `FINNIFTY`, `SENSEX`, `MIDCPNIFTY`) & Curated High-Beta NSE F&O Equities (~213 Stocks)  
> **Execution Engine:** Asynchronous Real-Time Scanner (Dhan HQ API v2 + Vectorized Mathematical Indicator Pipeline)  
> **Trading Philosophy:** Pure Option Buying with Directional Volatility Expansion, Trend Riding, Reversal Confirmation, and Direct Option Chart Scalping.

---

## Table of Contents
1. [Core Indicator & Mathematical Engine](#1-core-indicator--mathematical-engine)
2. [Setup 1: Volatility Squeeze & Range Expansion Breakout](#2-setup-1-volatility-squeeze--range-expansion-breakout)
3. [Setup 2: Walking the Bands with 9 EMA](#3-setup-2-walking-the-bands-with-9-ema)
4. [Setup 3: Bollinger W-Bottom & M-Top Reversals with RSI Divergence](#4-setup-3-bollinger-w-bottom--m-top-reversals-with-rsi-divergence)
5. [Setup 4: 9:30 AM Opening Range Breakout (ORB)](#5-setup-4-930-am-opening-range-breakout-orb)
6. [Setup 5: Standalone Option Chart Bollinger Scalper](#6-setup-5-standalone-option-chart-bollinger-scalper)
7. [The Two-Tier Stock Selection Funnel](#7-the-two-tier-stock-selection-funnel)
8. [Strike Selection Architecture & Risk Sizing](#8-strike-selection-architecture--risk-sizing)
9. [Paper Trading, Partial Booking & Exit Engine](#9-paper-trading-partial-booking--exit-engine)
10. [Architecture Summary & File Map](#10-architecture-summary--file-map)
11. [Runtime Settings, Entry Limits & Telemetry](#11-runtime-settings-entry-limits--telemetry)
12. [Stock Earnings Options (paper book)](#12-stock-earnings-options-paper-book)

---

## 1. Core Indicator & Mathematical Engine

All indicators are calculated vectorized via Pandas and NumPy in [`backend/app/services/indicators.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/indicators.py). The system operates on **5-minute candles** during market hours (09:15 to 15:30 IST).

```
   Upper Band = 20 SMA + (2.0 * Standard Deviation)
   ─────────────────────────────────────────────────
   Middle Band = 20-period Simple Moving Average (SMA)
   ─────────────────────────────────────────────────
   Lower Band = 20 SMA - (2.0 * Standard Deviation)
```

### Mathematical Definitions

1. **Bollinger Bands $(20, 2.0)$:**
   $$\text{Middle Band} = \text{SMA}_{20}(\text{Close})$$
   $$\sigma = \sqrt{\frac{1}{20} \sum_{i=1}^{20} (\text{Close}_i - \text{Middle Band})^2}$$
   $$\text{Upper Band} = \text{Middle Band} + 2.0 \cdot \sigma$$
   $$\text{Lower Band} = \text{Middle Band} - 2.0 \cdot \sigma$$

2. **BandWidth (Relative Volatility Meter):**
   $$\text{BandWidth} = \frac{\text{Upper Band} - \text{Lower Band}}{\text{Middle Band}} \times 100$$
   * **BandWidth 20-period Rolling Minimum ($\text{BW}_{20\text{-min}}$):** Computed across rolling 20 bars without zero-fill warm-up distortion to identify the absolute volatility compression baseline.

3. **Percent B ($\%B$ - Relative Band Position):**
   $$\%B = \frac{\text{Close} - \text{Lower Band}}{\text{Upper Band} - \text{Lower Band}}$$
   * $\%B > 1.0$: Price trading above Upper Band (Overbought / Expansion).
   * $\%B < 0.0$: Price trading below Lower Band (Oversold / Breakdown).
   * $\%B = 0.5$: Price exactly at 20 SMA Middle Band.

4. **Intraday Session VWAP (Volume Weighted Average Price):**
   $$\text{Typical Price}_i = \frac{\text{High}_i + \text{Low}_i + \text{Close}_i}{3}$$
   $$\text{Session VWAP}_t = \frac{\sum_{i=\text{session start}}^t (\text{Typical Price}_i \cdot \text{Volume}_i)}{\sum_{i=\text{session start}}^t \text{Volume}_i}$$
   * Resets strictly at **09:15:00 IST** at the start of each Indian trading day.
   * NaNs and zero volumes are guarded against division-by-zero errors.

5. **14-Period Wilder's RSI:**
   * Utilizes Wilder's exponential smoothing with smoothing factor $\alpha = \frac{1}{14}$.
   * Guards against zero loss (returns $100.0$) and zero gain (returns $0.0$).

6. **9-Period Exponential Moving Average (9 EMA):**
   * Acts as the dynamic trailing trend guide and pull-back trigger in trending phases.

7. **14-Period Average Directional Index (ADX) & Directional Movement ($+DI / -DI$):**
   * Computes True Range ($\text{TR}$), $+DM$, $-DM$.
   * Smoothed 14-period $+DI$ and $-DI$.
   * $\text{DX} = \frac{|+DI - -DI|}{+DI + -DI} \times 100$; smoothed 14-period $\text{ADX}$.
   * Identifies trend strength ($\text{ADX} > 23.0$) vs chop box ($\text{ADX} < 20.0$).

8. **15-Minute Opening Range (09:15 – 09:30 AM IST):**
   * Captures the high and low established during the first three 5-minute candles of the day.

---

## 2. Setup 1: Volatility Squeeze & Range Expansion Breakout

* **Setup Enum:** `SetupType.SETUP_1_SQUEEZE`
* **Underlying Principle:** John Bollinger's volatility compression principle. Following an extended contraction in BandWidth, volatility expansion produces high-gamma explosive moves ideal for option buying.

```
   BandWidth Compression (Squeeze)
   ───-·-·-·-·-·-·-·-·-·-·-·-·-·-·───
                                     \      ▲ Bullish Expansion (> Upper BB + > VWAP)
                                      \    /  BUY CE
                                       \──/
```

### Qualification Criteria

#### 1. Volatility Compression Check
The instrument must have recently entered a squeeze state:
$$\text{BandWidth} \le \text{BW}_{20\text{-min}} \times 1.30 \quad \text{OR} \quad \text{BandWidth} \le 5.0\%$$
*(Checked across the current or immediate previous candle).*

#### 2. BUY CE (Call Option) Trigger
1. **Band Penetration:** $\text{Close} > \text{Upper Band}$ (strong expansion).
2. **Institutional Bias:** $\text{Close} > \text{Session VWAP}$ (buyers in control).
3. **Momentum Confirmation:** $\text{Wilder RSI} \ge 58.0$.
4. **Execution Levels:**
   * **Spot Trigger:** $\text{Close}$
   * **Spot Stop-Loss:** $\max(\text{Middle Band}, \text{Candle Low} - 2.0)$
   * **Spot Target 1 (1:1.5 RR):** $\text{Close} + (1.5 \times \text{Risk})$
   * **Spot Target 2 (1:2.5 RR):** $\text{Close} + (2.5 \times \text{Risk})$
   * **Strike:** 1-Strike In-The-Money (ITM) CE.

#### 3. BUY PE (Put Option) Trigger
1. **Band Penetration:** $\text{Close} < \text{Lower Band}$ (strong breakdown).
2. **Institutional Bias:** $\text{Close} < \text{Session VWAP}$ (sellers in control).
3. **Momentum Confirmation:** $\text{Wilder RSI} \le 42.0$.
4. **Execution Levels:**
   * **Spot Trigger:** $\text{Close}$
   * **Spot Stop-Loss:** $\min(\text{Middle Band}, \text{Candle High} + 2.0)$
   * **Spot Target 1 (1:1.5 RR):** $\text{Close} - (1.5 \times \text{Risk})$
   * **Spot Target 2 (1:2.5 RR):** $\text{Close} - (2.5 \times \text{Risk})$
   * **Strike:** 1-Strike In-The-Money (ITM) PE.

---

## 3. Setup 2: Walking the Bands with 9 EMA

* **Setup Enum:** `SetupType.SETUP_2_WALKING`
* **Underlying Principle:** Strong momentum trends where prices hug the outer bands rather than reverting. Instead of chasing at the extremes, entries are timed on shallow pull-backs that test and hold the rising/falling 9 EMA.

```
   Upper Band  ───────────────────────────▲
                 ●       ● (Close > EMA 9)
   9 EMA       ───○───────○───────────────▲  <-- Entry on bounce/touch
                 (Pullback touches 9 EMA)
   20 SMA Middle ─────────────────────────▲
```

### Qualification Criteria

#### 1. Trend Strength Qualifier
* Minimum lookback of 22 bars available.
* $\text{ADX} \ge 23.0$ (prohibits taking walking entries in ranging or consolidating markets).

#### 2. BUY CE (Call Option) Trigger
1. **Prior Momentum Walk:** At least one of the prior 2 candles closed at or above the Upper Band:
   $$\text{Close}_{t-1} \ge \text{Upper Band}_{t-1} \times 0.998 \quad \text{OR} \quad \text{Close}_{t-2} \ge \text{Upper Band}_{t-2} \times 0.998$$
2. **Expansion Filter:** Upper Band must be expanding upward, not curling down into consolidation:
   $$\text{Upper Band}_t \ge \text{Upper Band}_{t-1}$$
3. **Directional Flow:** $+DI \ge -DI$ (positive directional dominance).
4. **Moving Average Alignment:** $9\text{ EMA} > \text{Middle Band}$ and $\text{Close} > 9\text{ EMA}$ and $\text{Close} > \text{VWAP}$.
5. **9 EMA Pullback Touch:** Current candle low retests 9 EMA and closes bullish:
   $$\text{Low} \le \max(9\text{ EMA} \times 1.004,\, 9\text{ EMA} + 0.5) \quad \text{AND} \quad \text{Close} \ge \text{Open}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** Placed snugly below the 9 EMA:
     $$\text{SL} = 9\text{ EMA} - \max(\text{Bar Range} \times 0.4,\, \text{Close} \times 0.001)$$
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM CE.

#### 3. BUY PE (Put Option) Trigger
1. **Prior Momentum Walk:** Prior candle closed at or below Lower Band:
   $$\text{Close}_{t-1} \le \text{Lower Band}_{t-1} \times 1.002 \quad \text{OR} \quad \text{Close}_{t-2} \le \text{Lower Band}_{t-2} \times 1.002$$
2. **Expansion Filter:** Lower Band must be expanding downward:
   $$\text{Lower Band}_t \le \text{Lower Band}_{t-1}$$
3. **Directional Flow:** $-DI \ge +DI$ (negative directional dominance).
4. **Moving Average Alignment:** $9\text{ EMA} < \text{Middle Band}$ and $\text{Close} < 9\text{ EMA}$ and $\text{Close} < \text{VWAP}$.
5. **9 EMA Pullback Retest:** Current candle high retests 9 EMA and closes bearish:
   $$\text{High} \ge \min(9\text{ EMA} \times 0.996,\, 9\text{ EMA} - 0.5) \quad \text{AND} \quad \text{Close} \le \text{Open}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** Placed snugly above the 9 EMA:
     $$\text{SL} = 9\text{ EMA} + \max(\text{Bar Range} \times 0.4,\, \text{Close} \times 0.001)$$
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM PE.

---

## 4. Setup 3: Bollinger W-Bottom & M-Top Reversals with RSI Divergence

* **Setup Enum:** `SetupType.SETUP_3_REVERSAL`
* **Underlying Principle:** Classical Arthur Merrill & John Bollinger reversal patterns. The first leg pierces outside the band; the second leg holds inside the band, accompanied by strong momentum divergence on Wilder's RSI.

```
   W-Bottom (BUY CE)                      M-Top (BUY PE)
        Peak (P)                               Valley (V)
         /\                                     \  /
        /  \     Trigger: Breakout               \/    Trigger: Breakdown
       /    \    above P                          \
   ───/──────\─────── Upper BB            ───/\────/\── Upper BB
     /        \                             /  \  /  \
    /  (L2)    \                           / (H1)(H2) \
  (L1) Holds   Inside Lower BB           Pierces Holds
 Pierces                                 Band    Inside Band
 Band
```

### Qualification Criteria

#### 1. W-Bottom Reversal (BUY CE)
1. **First Low ($L_1$):** Formed within the last 5 to 20 candles where $\text{Low}_{L_1} \le \text{Lower Band}_{L_1}$ (outside or piercing the band).
2. **Intermediate Peak ($P$):** A bounce toward the 20 SMA middle band separates the two bottoms.
3. **Second Low ($L_2$):** Formed more recently with a higher or equal low that stays **inside** the band:
   $$\text{Low}_{L_2} \ge \text{Low}_{L_1} \times 0.995 \quad \text{AND} \quad \text{Low}_{L_2} > \text{Lower Band}_{L_2}$$
4. **Bullish RSI Divergence:** Momentum weakens on the selling side:
   $$\text{RSI}(L_2) > \text{RSI}(L_1) + 1.5$$
5. **Confirmation Trigger:** Current candle closes above intermediate peak $P$ and above the 9 EMA:
   $$\text{Close} > P_{\text{high}} \quad \text{AND} \quad \text{Close} > 9\text{ EMA}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** Placed below the second low: $\text{SL} = \text{Low}_{L_2} - 2.0$.
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM CE.

#### 2. M-Top Reversal (BUY PE)
1. **First High ($H_1$):** Formed within the last 5 to 20 candles where $\text{High}_{H_1} \ge \text{Upper Band}_{H_1}$ (piercing the band).
2. **Intermediate Valley ($V$):** A pull-back toward the 20 SMA middle band.
3. **Second High ($H_2$):** Formed more recently with a lower or equal high staying **inside** the band:
   $$\text{High}_{H_2} \le \text{High}_{H_1} \times 1.005 \quad \text{AND} \quad \text{High}_{H_2} < \text{Upper Band}_{H_2}$$
4. **Bearish RSI Divergence:** Momentum drops on the buying side:
   $$\text{RSI}(H_2) < \text{RSI}(H_1) - 1.5$$
5. **Confirmation Trigger:** Current candle closes below intermediate valley $V$ and below the 9 EMA:
   $$\text{Close} < V_{\text{low}} \quad \text{AND} \quad \text{Close} < 9\text{ EMA}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** Placed above the second high: $\text{SL} = \text{High}_{H_2} + 2.0$.
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM PE.

---

## 5. Setup 4: 9:30 AM Opening Range Breakout (ORB)

* **Setup Enum:** `SetupType.SETUP_4_ORB`
* **Underlying Principle:** The 15-minute Opening Range (09:15 to 09:30 AM IST) captures opening institutional price discovery. When accompanied by Bollinger Band expansion and VWAP directional separation, opening range breaks initiate high-velocity morning trends.

```
   09:15 - 09:30 AM IST
   ┌───────────────────────┐ OR High
   │  15-min Opening Range │
   └───────────────────────┘ OR Low
               │
               ▼  (09:30 to 11:30 AM IST Window)
               ● Close > OR High + Close > Upper BB + Close > VWAP ==> BUY CE
```

### Qualification Criteria

#### 1. Time-Window Filter
* **Active Window:** Strictly between **09:30 AM and 11:30 AM IST**. After 11:30 AM, market enters midday chop; new ORB entries are automatically disabled.
* **Intraday Hard Cutoff:** Strictly before **15:15 IST** (no entries in the final 15 minutes of trading).

#### 2. BUY CE (Call Option) Trigger
1. **OR High Break:** Current candle closes strictly above the 15-min Opening Range High:
   $$\text{Close} > \text{OR}_{\text{high}}$$
2. **Bollinger Band Alignment:** $\text{Close} > \text{Upper Band}$ (volatility confirming the move).
3. **Session VWAP Alignment:** $\text{Close} > \text{Session VWAP}$.
4. **Execution Levels:**
   * **Spot Stop-Loss:** $\max(\text{Middle Band}, \text{OR}_{\text{high}} - 2.0)$
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM CE.

#### 3. BUY PE (Put Option) Trigger
1. **OR Low Break:** Current candle closes strictly below the 15-min Opening Range Low:
   $$\text{Close} < \text{OR}_{\text{low}}$$
2. **Bollinger Band Alignment:** $\text{Close} < \text{Lower Band}$.
3. **Session VWAP Alignment:** $\text{Close} < \text{Session VWAP}$.
4. **Execution Levels:**
   * **Spot Stop-Loss:** $\min(\text{Middle Band}, \text{OR}_{\text{low}} + 2.0)$
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM PE.

---

## 6. Setup 5: Standalone Option Chart Bollinger Scalper

* **Setup Enum:** `SetupType.SETUP_5_OPTION_BB`
* **File Reference:** [`backend/app/services/option_chart_strategy.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/option_chart_strategy.py)
* **Underlying Principle:** Independent technical analysis executed **directly on the live option premium chart** (ATM CE and ATM PE candles). Spot index or equity price moves are completely decoupled from entry and exit decisions.

```
   Option Premium Candle Chart (e.g. NIFTY 22500 CE)
   ──────────────────────────────────────────────────
   Upper BB  ─────────────────────────────▲
                                         ● Close > Option Upper BB
   Option VWAP ──────────────────────────▲ (Buyers dominating premium)
   9 EMA     ─────────────────────────────▲
                                         ▲ Volume Surge >= 1.2x 20-bar avg
```

### Qualification Criteria

Evaluated on 5-minute candles accumulated from real Dhan exchange option quotes:
1. **Option Upper Bollinger Band Breakout:**
   $$\text{Option Close} > \text{Option Upper Band}$$
2. **Option Session VWAP Dominance:**
   $$\text{Option Close} > \text{Option Session VWAP}$$
   *(If premium is below VWAP, option writers/sellers are in control; trade is rejected).*
3. **Option Momentum Confirmation:**
   $$\text{Option Wilder RSI} \ge 58.0$$
4. **Volume Surge & Illiquid Option Protection:**
   $$\text{Option Volume} \ge \max(1000\text{ contracts},\, 1.2 \times \text{Avg Volume}_{20\text{-bar}})$$
   *(Protects against false breakouts on illiquid far-strike contracts).*

### Dynamic Risk & Targets (Option Points)
* **Option Stop-Loss:** Anchored below the option 9 EMA or the breakout bar's low with a minimum 4% buffer:
  $$\text{Bar Range} = \max(\text{High} - \text{Low},\, \text{Close} \times 0.04)$$
  $$\text{Risk Pts} = \max(\text{Close} - 9\text{ EMA},\, \text{Bar Range} \times 0.5,\, \text{Close} \times 0.04)$$
  $$\text{Option SL Price} = \max(0.5,\, \text{Close} - \text{Risk Pts})$$
* **Option Target 1 (+1.5R):** $\text{Close} + (\text{Risk Pts} \times 1.5)$
* **Option Target 2 (+2.5R):** $\text{Close} + (\text{Risk Pts} \times 2.5)$

### Strict Option-Chart-Only Exit Execution
In [`paper_trader.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/paper_trader.py#L275-L325), Setup 5 positions **never check underlying spot price**:
* **Stop-Loss Hit:** $\text{LTP}_{\text{option}} \le \text{Option SL}$
* **Target 1 Hit:** $\text{LTP}_{\text{option}} \ge \text{Option T1}$ (Books 50% lots and trails Option SL to Entry).
* **Target 2 Hit:** $\text{LTP}_{\text{option}} \ge \text{Option T2}$ (Full exit).
* **Underlying Spot Decoupling:** Even if the underlying stock swings violently, the Setup 5 position remains open unless the option chart premium hits its defined technical levels.

---

## 7. The Two-Tier Stock Selection Funnel

* **File References:** [`backend/app/services/momentum_ranker.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/momentum_ranker.py) & [`backend/app/services/scanner_worker.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/scanner_worker.py)
* **Goal:** Screen all ~213 NSE F&O equities in real time without triggering API rate limits or taking low-probability chop trades.

```
       [All 213 NSE F&O Stocks]
                  │
                  ▼  (Tier 1: High-Speed Batch Marketfeed)
       [MomentumRanker Algorithm]
         • Day % Change (40%)
         • VWAP Distance (30%)
         • Day Range Position (30%)
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
  Top 5 Bullish       Top 5 Bearish
  (Change >= +0.75%)  (Change <= -0.75%)
  (LTP > VWAP)        (LTP < VWAP)
  (Range Pos >= 65%)  (Range Pos <= 35%)
        │                   │
        └─────────┬─────────┘
                  ▼  (Tier 2: Deep 5m Bollinger Bands Scanning)
       [Top 10 Stocks + 4 Indices + Active Positions]
                  │
                  ▼  (Market Confluence Guard)
       • Bullish Stock + Nifty Bullish ==> BUY CE
       • Bearish Stock + Nifty Bearish ==> BUY PE
       • Neutral / Counter-Trend       ==> DISCARDED
```

### Tier 1: Real-Time Momentum Ranking
Every cycle, marketfeed quotes are fetched across all F&O securities. For each stock:
$$\text{Composite Score} = (\text{Change \%} \times 0.40) + (\text{VWAP Dist \%} \times 0.30) + ((\text{Range Pos \%} - 50) \times 0.30)$$
* **Top 5 Bullish:** Highest positive scores.
* **Top 5 Bearish:** Most negative scores.

### Tier 2: Deep Bollinger Scanning
Deep historical candle calculations are executed **only** on:
1. 4 Benchmark Indices (`NIFTY 50`, `NIFTY BANK`, `FINNIFTY`, `SENSEX`).
2. Top 5 Bullish Stocks.
3. Top 5 Bearish Stocks.
4. Active Paper Positions (for continuous exit monitoring).

### Market Confluence Rules
* **Directional Alignment:** A Bullish ranked stock can **only trigger CE**. A Bearish ranked stock can **only trigger PE**.
* **Macro Filter:** `NIFTY 50` status sets macro market bias:
  * Nifty above VWAP $\to$ **Macro Bullish** $\to$ Bearish stock PE entries blocked.
  * Nifty below VWAP $\to$ **Macro Bearish** $\to$ Bullish stock CE entries blocked.

---

## 8. Strike Selection Architecture & Risk Sizing

* **File Reference:** [`backend/app/services/strike_selector.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/strike_selector.py)

### Strike Step Matrix

| Instrument Category | Strike Step ($\Delta S$) | Example (Spot $\to$ ATM) |
| :--- | :--- | :--- |
| **NIFTY 50 / FINNIFTY** | 50 points | Spot 22,480 $\to$ ATM 22,500 |
| **BANK NIFTY / SENSEX** | 100 points | Spot 48,130 $\to$ ATM 48,100 |
| **MIDCPNIFTY** | 25 points | Spot 12,010 $\to$ ATM 12,000 |
| **High-Price Stocks** (Maruti) | 100 points | Spot 12,460 $\to$ ATM 12,500 |
| **Mid-Price Stocks** (TCS, Bajaj Fin) | 50 points | Spot 4,025 $\to$ ATM 4,000 |
| **Standard Stocks** (Reliance, Infy) | 20 points | Spot 2,986 $\to$ ATM 2,980 |
| **Banking Stocks** (HDFC, ICICI, Axis) | 10 points | Spot 1,692 $\to$ ATM 1,690 |
| **Sub-₹500 Stocks** (SBI, ITC) | 5 points | Spot 818 $\to$ ATM 820 |
| **Sub-₹200 Stocks** (Tata Steel) | 2 points | Spot 162 $\to$ ATM 162 |

### 1-Strike In-The-Money (ITM) Formula (Setups 1 – 4)
* **For CE:** $\text{Strike} = \text{ATM} - \Delta S$
* **For PE:** $\text{Strike} = \text{ATM} + \Delta S$
* **Advantages:** Optimal Delta ($\Delta \approx 0.55 - 0.65$), substantial intrinsic value buffer against theta decay, and deep liquidity.

### ATM Formula (Setup 5)
* **For CE & PE:** $\text{Strike} = \text{ATM}$ (maximum volatility expansion and highest options liquidity).

### Position Sizing & Maximum Risk Cap
In [`paper_trader.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/paper_trader.py#L160-L175):
$$\text{Risk per Lot (₹)} = (\text{Option Entry} - \text{Option SL}) \times \text{Official Lot Size}$$
* **Capital Protection Rule:** If $\text{Risk per Lot} > 2.0 \times \text{Max Risk Cap}$ (default ₹8,000), the trade is **automatically skipped**.
* **Allowed Lots:**
  $$\text{Lots} = \min\left(\text{Default Lots},\, \max\left(1,\, \left\lfloor\frac{\text{Max Risk Cap}}{\text{Risk per Lot}}\right\rfloor\right)\right)$$

---

## 9. Paper Trading, Partial Booking & Exit Engine

* **File References:** [`backend/app/services/paper_trader.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/paper_trader.py) & [`backend/app/services/paper_storage.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/paper_storage.py)

```
   Position Opened (Default 2 Lots)
               │
               ▼
   Target 1 Hit (1:1.5 RR)
   ┌──────────────────────────────────────────────┐
   │ • Book 50% Position (1 Lot locked in profit) │
   │ • Trail Stop-Loss of Runner to Breakeven     │
   └──────────────────────────────────────────────┘
               │
        ┌──────┴──────┐
        ▼             ▼
   Target 2 Hit    Breakeven Trailed SL Hit
   (1:2.5 RR)      (LTP returns to Entry)
   Full Exit       Runner closed at ₹0 P&L
   Maximum Profit  50% Target 1 Profit RETAINED!
```

### 1. Partial Profit Booking & Breakeven Trailing
* **Default Quantity:** 2 Lots (configurable by the user).
* **Target 1 Execution:** When price hits Target 1 (+1.5R):
  1. Closes $\lfloor\frac{\text{Lots}}{2}\rfloor$ lots immediately.
  2. Records realized profit in `booked_pnl_rupees`.
  3. Automatically updates $\text{Option SL} = \text{Option Entry}$ (breakeven).
* **Runner Protection:** If the remaining runner reverses and hits the trailed SL, the runner exits at ₹0 P&L, **preserving the profit booked at Target 1**.
* **Target 2 Execution:** When price hits Target 2 (+2.5R), all remaining lots exit.

### 2. Anti-Churn Chop Box Re-Entry Gating
* If a trade is stopped out, the system prevents taking continuous re-entries in the same sideways chop box:
  * **Setups 1–4 (CE):** New trade blocked unless $\text{Spot Entry} > \text{Previous Stopped-Out Entry}$.
  * **Setups 1–4 (PE):** New trade blocked unless $\text{Spot Entry} < \text{Previous Stopped-Out Entry}$.
  * **Setup 5:** New trade blocked unless $\text{Option Entry} > \text{Previous Stopped-Out Option Entry}$.

### 3. Persistent SQLite Storage
* Realized trades, active positions, performance metrics, and processed signal IDs are committed atomically to SQLite (`data/trades.db`).
* System restarts or server reboots reload portfolio state cleanly with zero data loss.

---

## 10. Architecture Summary & File Map

| Component | File Path | Core Functionality |
| :--- | :--- | :--- |
| **Indicators Engine** | [`backend/app/services/indicators.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/indicators.py) | Vectorized Bollinger Bands, VWAP, RSI, EMA 9, ADX, ORB. |
| **Strategy Engine** | [`backend/app/services/strategy_engine.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/strategy_engine.py) | Evaluates Setups 1, 2, 3, and 4 with bias filters. |
| **Relative Strength (Setup 9)** | [`backend/app/services/relative_strength.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/relative_strength.py) | Setup 9: stock vs NIFTY relative strength, first 9 EMA pullback. |
| **Option Scalper** | [`backend/app/services/option_chart_strategy.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/option_chart_strategy.py) | Standalone Setup 5 option chart Bollinger Band scalper. |
| **Strike Selector** | [`backend/app/services/strike_selector.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/strike_selector.py) | 1-Strike ITM and ATM resolution, Dhan `/optionchain` matching. |
| **Momentum Ranker**| [`backend/app/services/momentum_ranker.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/momentum_ranker.py) | Real-time F&O stock momentum scoring and classification. |
| **Scanner Worker** | [`backend/app/services/scanner_worker.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/scanner_worker.py) | Two-tier cyclic scan loop, SSE state broadcast. |
| **Paper Trader**   | [`backend/app/services/paper_trader.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/paper_trader.py) | Forward-testing journal, partial booking, re-entry gate. |
| **Dhan HQ Client** | [`backend/app/services/dhan_client.py`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/backend/app/services/dhan_client.py) | Async throttled client, 429 retry backoff, zero-token auth. |
| **Frontend UI**    | [`frontend/src/App.tsx`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/frontend/src/App.tsx) | Live dashboard with Hero Radar, Setup tabs, Paper Journal. |


---

## 11. Implementation Status vs. This Specification (audit of 2026-10-14)

This section records where the code deliberately or accidentally differs from sections 1–10. The code is the source of truth for live behaviour until a decision below says otherwise.

### 11.1 Setups 6–8 (snap-back family) are implemented but were not specified above
All three require `BandWidth > SQUEEZE_ABS_BW_PCT` ("bands are wide") and use a 1-strike ITM strike, with targets at the 20 SMA (Target 1) and the opposite band (Target 2).

| Setup | Enum | Trigger (PE shown; CE is the mirror) |
|---|---|---|
| 6 | `SETUP_6_PINBAR_SNAPBACK` | `ADX <= 25`; high pierces the upper band, close back inside, upper wick >= 50% of the bar range, body in the lower 60%, `RSI >= 68`, close above the 20 SMA. SL above the pin-bar high. |
| 7 | `SETUP_7_INSIDE_BAR_SNAPBACK` | Bar t-2 reaches the 2.5σ band, bar t-1 is an inside bar, bar t closes below the inside bar's low, close above the 20 SMA. SL above the mother-bar high. |
| 8 | `SETUP_8_DIVERGENCE_SNAPBACK` | Climax swing with RSI divergence fading back toward the mean (see `strategy_engine.py`, Setup 8 block). |

### 11.2 Setup 3 differs from section 4 (decision needed; not changed)
| Rule | Spec (section 4) | Code |
|---|---|---|
| Swing window | Leg 1 5–20 candles back | Last 12 candles, split 6 / 6 |
| Second low | `Low2 >= Low1 × 0.995` and inside band | Only `close2 > lower band` |
| RSI divergence | `RSI2 > RSI1 + 1.5` | `RSI2 > RSI1` (no margin) |
| Trigger | Close > peak high **and** above 9 EMA | Close crosses the neckline (max high between the lows); 9 EMA not checked |
| Stop-loss | Second low − 2.0 | Lower of both lows − 1.0 |

Tightening the code to the spec would reduce Setup 3 signal frequency; loosening the spec to the code keeps current behaviour. This needs an owner decision.

### 11.3 Stock ranking and risk cap
* The momentum ranker is constructed with `top_n = 10` in `scanner_worker.py` (the class default and section 7 say 5).
* The risk cap skips a trade when risk per lot exceeds **1×** the max risk cap (`paper_trader.py`), not 2× as section 8 states.

### 11.4 Changes made after this spec was written
* VWAP for instruments with no volume (cash indices) is the session-cumulative mean of typical price, not the single bar's typical price.
* RSI / ATR / DI / ADX use Wilder smoothing seeded with an SMA; ADX is undefined (neutral 20) before bar 28.
* "Bands are wide / squeeze" uses `SQUEEZE_ABS_BW_PCT` (default 5.0 = legacy; nearly always true on 5m bars). Recalibrate with `scripts/compare_squeeze.py` on recorded candles.
* Option exits scale spot risk by the contract's chain delta; when the chain has no Greek the default 0.50–0.55 is used and the recommendation carries `delta_assumed = true` (`REQUIRE_REAL_DELTA=1` refuses such entries).
* Setup 5 stops entering after 14:30 IST on the contract's expiry day.
* Size defaults scale with the 2-lot default: `max_risk_per_trade` 8,000 (was 4,000) and `MAX_OPEN_NOTIONAL` 20 lakh (was 10 lakh, env override `MAX_OPEN_NOTIONAL`). Position-count caps (8 open, 3 entries per stock per day) are unchanged.


---

## 12. Setup 9: Relative Strength vs NIFTY (First 9 EMA Pullback)

Trades stocks that move on their own momentum: rising while NIFTY is flat or falling (BUY CE), or falling while NIFTY is flat or rising (BUY PE). Implemented in `relative_strength.py`; all rules below use completed 5m bars only.

### Qualification (CE shown; PE is the mirror)
1. **Funnel:** the stock is in the momentum ranker's `top_bullish` list (`top_bearish` for PE). Stocks only; indices are never traded by this setup.
2. **Relative strength:** measured from today's first 5m open. Stock move `>= +0.75%`, NIFTY 50 move `<= +0.15%` (flat or falling), and stock move minus NIFTY move `>= 0.75` points. PE: stock `<= -0.75%`, NIFTY `>= -0.15%`, NIFTY minus stock `>= 0.75`.
3. **Trend intact:** the pullback bar closes above session VWAP (below for PE) and the 9 EMA is higher than three bars earlier (lower for PE).
4. **First pullback:** the previous bar did not touch the 9 EMA, and no bar since the relative-strength condition first held has touched it.
5. **Trigger:** the bar's low reaches the 9 EMA (within 0.1%), and it closes above the EMA and above its own open (below both for PE). The signal fires at that bar's close, never on a forming bar.
6. **Window:** at least 6 bars today, bar start between 09:45 and 15:10 IST, so the last confirmation lands at the 15:15 fresh-entry cutoff. NIFTY must have closed the same bar (a lagging index skips the bar rather than using a stale close). The setup runs in live mode only, so it never appears in demo.

### Risk
* Entry: the confirming bar's close. Stop: pullback low minus `max(0.5, 0.05%)` (pullback high plus the same buffer for PE), widened to the minimum risk by `recommend_strike`.
* Target 1 = 1.5R, Target 2 = 2.5R (the default `recommend_strike` ladder). Default 1-strike ITM contract.
* Existing sizing (2 lots), risk and notional caps, partial booking and the re-entry gate apply unchanged.

### Notes
* The NIFTY market-bias veto used by Setups 1–8 is deliberately **not** applied: this setup wants the stock to diverge from NIFTY.
* The thresholds (0.75%, 0.15%) are starting values, not tuned on recorded candles.

---

## 11. Runtime Settings, Entry Limits & Telemetry

Every limit below is a **runtime setting**: editable from the dashboard's Settings tab (or `PUT /api/settings`), validated, saved in the database, written to an audit trail (`settings_audit`) and applied to the next decision with no restart. A saved value wins; otherwise the environment default (`app/core/config.py`) applies. Definitions live in [`runtime_settings.py`](backend/app/services/runtime_settings.py).

### New entry limits (all apply to Setups 1–9 in each book; 0 switches a limit off)
| Setting | Effect |
|---|---|
| `max_lots_per_trade` | Hard ceiling on lots per entry, applied after the risk-based sizing in section 8. Default 0 (off). |
| `max_entries_per_day` | Most entries per book per IST day across all symbols. Default 0 (off). |
| `max_consecutive_losses` | After this many losing trades in a row today, new entries in that book pause until a winner closes or the next IST day. Default 0 (off). |

Existing limits are now runtime settings too, with the same defaults as before: `daily_loss_limit`, `max_open_positions`, `max_open_notional`, `max_entries_per_symbol_per_day`, `reentry_cooldown_seconds`, `default_lots`, `max_risk_per_trade`, `max_quote_age_seconds`, `max_entry_spread_pct`, `gap_exit_pct`.

### Telemetry (no change to any setup rule)
* `strategy_decisions`: every ENTERED / SKIPPED / EXITED decision with a reason code (e.g. `MAX_OPEN_POSITIONS`, `SPREAD_TOO_WIDE`, `LOSS_CAP`, `SETUP_SWITCHED_OFF`) and the numbers behind it.
* `trade_excursions`: per trade MFE (best open profit) and MAE (worst open loss) in rupees, plus final P&L.
* `error_events`: warnings and errors from the app's loggers, grouped under a short code.
* `GET /api/telemetry/performance` reports expectancy, profit factor, drawdown, longest loss streak, MFE capture, by setup, symbol, entry hour and exit reason. Switches: `telemetry_enabled`, `telemetry_jsonl_enabled`, `telemetry_skip_logging`, `telemetry_retention_days`.

---

## 12. Stock Earnings Options (paper book)

A separate paper book (`earnings` in the decision trail), **paper only**, off by default (`earnings_enabled`). Code: [`earnings_strategy.py`](backend/app/services/earnings_strategy.py) (rules), [`earnings_engine.py`](backend/app/services/earnings_engine.py) (book, Dhan chain provider). Stocks, lot sizes and security ids come from `backend/app/data/fno_universe.json`; the earnings calendar (symbol, date, session BMO/AMC, sector) is entered in the Earnings tab. Every number below is a runtime setting (`earnings_*`).

**Timing.** The market reacts on the announcement day for BMO (before open) and on the next trading day for AMC (after close) or a non-trading date. The last safe close is the trading day before the reaction day. Calendar rows with no session follow `earnings_default_session` (default SKIP: not traded).

**Mode A, pre-earnings run-up (long ATM straddle).**
* Entry: earnings between `earnings_mode_a_near_days` and `earnings_mode_a_far_days` calendar days away (default 8 to 12), after `earnings_entry_time`; ATM strike from the live chain; bought at the ask. Refused when IV percentile is above `earnings_mode_a_max_ivp` (default 40, 0 = off; needs `earnings_iv_min_history` days of stored IV, else `earnings_iv_missing_policy`), when a leg's spread exceeds `earnings_max_spread_pct`, or when premium exceeds `earnings_max_capital_per_trade`.
* Expiry: the earliest listed expiry at least `earnings_min_days_to_expiry` days after the exit date (rolls to the next expiry automatically).
* Exit, first to fire: loss of `earnings_mode_a_max_loss_pct` of the premium (default 40, 0 = off); expiry closer than the minimum; scheduled exit `earnings_mode_a_exit_days_before` trading days before the last safe close, at `earnings_exit_time`.

**Mode B, post-earnings IV crush (defined-risk iron condor).**
* Entry: on the last safe close day; short strikes `earnings_condor_short_steps` grid steps from ATM, wings `earnings_condor_wing_steps` beyond; shorts sold at the bid, wings bought at the ask. Refused when net credit is at or below `earnings_min_condor_credit`, IV rank is below `earnings_mode_b_min_ivr` (default 0 = off), spreads are too wide, or max risk exceeds the capital cap.
* Exit, first to fire: spot at or beyond either short strike; expiry closer than the minimum; reaction day at `earnings_mode_b_exit_time`.

**Risk gates (every entry).** Kill switch, daily loss limit, consecutive-loss pause, `max_entries_per_day`, `max_open_notional` (on max risk), `earnings_max_positions`, one position per sector (`earnings_one_per_sector`), one position per stock, lots = `earnings_lots` capped by `max_lots_per_trade`. The kill switch also squares off this book. Positions are never entered or exited on a quote that could not be refreshed; a scheduled exit more than a day overdue closes at the last known prices.

**Costs.** Charges per leg use the same calculator as the other setups.

