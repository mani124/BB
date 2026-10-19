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
16. [Runtime Settings, Entry Limits & Telemetry](#16-runtime-settings-entry-limits--telemetry)
17. [Stock Earnings Options (paper book)](#17-stock-earnings-options-paper-book)
20. [Setup 15: ATR Trend Flip (swing equity book)](#20-setup-15-atr-trend-flip-swing-equity-book)
21. [Setup 16: Option Squeeze Breakout](#21-setup-16-option-squeeze-breakout)

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
* Minimum lookback of 22 bars available, and at least 20 bars of the current session (so the bands are not distorted by the overnight gap).
* $\text{ADX} \ge 23.0$ (prohibits taking walking entries in ranging or consolidating markets). ADX is neutral (20) until 28 bars exist.

#### 2. BUY CE (Call Option) Trigger
1. **Prior Momentum Walk:** At least one of the prior 2 candles closed in the top 10% of the band or above it (width $W = \text{Upper} - \text{Lower}$):
   $$\text{Close}_{t-k} \ge \text{Upper Band}_{t-k} - 0.1\,W_{t-k}, \quad k \in \{1, 2\}$$
2. **Expansion Filter:** Upper Band must be expanding upward, not curling down into consolidation:
   $$\text{Upper Band}_t \ge \text{Upper Band}_{t-1}$$
3. **Directional Flow:** $+DI \ge -DI$ (positive directional dominance).
4. **Moving Average Alignment:** $9\text{ EMA} > \text{Middle Band}$ and $\text{Close} > 9\text{ EMA}$ and $\text{Close} > \text{VWAP}$.
5. **9 EMA Pullback Touch:** Current candle low retests 9 EMA and closes bullish:
   $$\text{Low} \le 9\text{ EMA} + 0.25 \cdot \text{ATR}_{14} \quad \text{AND} \quad \text{Close} \ge \text{Open}$$
   (without ATR the pad is 0.1% of the EMA)
6. **Execution Levels:**
   * **Spot Stop-Loss:** Below the lower of the 9 EMA and the signal bar's low:
     $$\text{SL} = \min(9\text{ EMA}, \text{Low}) - \max(\text{Bar Range} \times 0.25,\, \text{Close} \times 0.0005)$$
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM CE.

#### 3. BUY PE (Put Option) Trigger
1. **Prior Momentum Walk:** At least one of the prior 2 candles closed in the bottom 10% of the band or below it:
   $$\text{Close}_{t-k} \le \text{Lower Band}_{t-k} + 0.1\,W_{t-k}, \quad k \in \{1, 2\}$$
2. **Expansion Filter:** Lower Band must be expanding downward:
   $$\text{Lower Band}_t \le \text{Lower Band}_{t-1}$$
3. **Directional Flow:** $-DI \ge +DI$ (negative directional dominance).
4. **Moving Average Alignment:** $9\text{ EMA} < \text{Middle Band}$ and $\text{Close} < 9\text{ EMA}$ and $\text{Close} < \text{VWAP}$.
5. **9 EMA Pullback Retest:** Current candle high retests 9 EMA and closes bearish:
   $$\text{High} \ge 9\text{ EMA} - 0.25 \cdot \text{ATR}_{14} \quad \text{AND} \quad \text{Close} \le \text{Open}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** Above the higher of the 9 EMA and the signal bar's high:
     $$\text{SL} = \max(9\text{ EMA}, \text{High}) + \max(\text{Bar Range} \times 0.25,\, \text{Close} \times 0.0005)$$
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

**Session gate:** at least 20 bars of the current session must exist (overnight-gap distortion of bands and RSI).

#### 1. W-Bottom Reversal (BUY CE)
1. **First Low ($L_1$):** Formed 5 to 20 candles before the trigger candle where $\text{Low}_{L_1} \le \text{Lower Band}_{L_1}$ (outside or piercing the band). If several bars pierce, the lowest one is $L_1$.
2. **Intermediate Peak ($P$):** A bounce toward the 20 SMA middle band separates the two bottoms.
3. **Second Low ($L_2$):** The lowest low of the last 5 candles (trigger candle excluded) that is at least 3 candles after $L_1$, a higher or equal low (within a small ATR tolerance) that stays **inside** the band:
   $$\text{Low}_{L_2} \ge \text{Low}_{L_1} - 0.25 \times \text{ATR}(14) \quad \text{AND} \quad \text{Low}_{L_2} > \text{Lower Band}_{L_2}$$
   (ATR tolerance replaces the earlier flat `x 0.995`, which is 125 points on NIFTY and rejected nothing.)
4. **Bullish RSI Divergence:** Momentum weakens on the selling side:
   $$\text{RSI}(L_2) > \text{RSI}(L_1) + 1.5$$
5. **Confirmation Trigger:** Current candle closes above intermediate peak $P$ and above the 9 EMA:
   $$\text{Close} > P_{\text{high}} \quad \text{AND} \quad \text{Close} > 9\text{ EMA}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** $\text{SL} = \text{Low}_{L_2} - 0.1 \times \text{ATR}(14)$ (then widened to the minimum risk floor if needed).
   * **Spot Targets:** 1:1.5 RR (Target 1), 1:2.5 RR (Target 2).
   * **Strike:** 1-Strike ITM CE.

#### 2. M-Top Reversal (BUY PE)
1. **First High ($H_1$):** Formed 5 to 20 candles before the trigger candle where $\text{High}_{H_1} \ge \text{Upper Band}_{H_1}$ (piercing the band). If several bars pierce, the highest one is $H_1$.
2. **Intermediate Valley ($V$):** A pull-back toward the 20 SMA middle band.
3. **Second High ($H_2$):** The highest high of the last 5 candles (trigger candle excluded) that is at least 3 candles after $H_1$, a lower or equal high (within a small ATR tolerance) staying **inside** the band:
   $$\text{High}_{H_2} \le \text{High}_{H_1} + 0.25 \times \text{ATR}(14) \quad \text{AND} \quad \text{High}_{H_2} < \text{Upper Band}_{H_2}$$
4. **Bearish RSI Divergence:** Momentum drops on the buying side:
   $$\text{RSI}(H_2) < \text{RSI}(H_1) - 1.5$$
5. **Confirmation Trigger:** Current candle closes below intermediate valley $V$ and below the 9 EMA:
   $$\text{Close} < V_{\text{low}} \quad \text{AND} \quad \text{Close} < 9\text{ EMA}$$
6. **Execution Levels:**
   * **Spot Stop-Loss:** $\text{SL} = \text{High}_{H_2} + 0.1 \times \text{ATR}(14)$ (then widened to the minimum risk floor if needed).
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
1. 6 Benchmark Indices (`NIFTY 50`, `NIFTY BANK`, `FINNIFTY`, `SENSEX`, `MIDCPNIFTY`, `NIFTYNXT50`).
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
  * The gate only looks at a stop-out **from the same IST day and the same book** (demo or live); an older or other-book stop-out never blocks a new entry.

### 2a. Entry Validity and End-of-Day Fill
* **Entry validity (live book, Setups other than 5):** a signal is skipped (reason `SETUP_NO_LONGER_VALID`) when the latest underlying price (at most 2 minutes old) is already at or beyond the signal's stop, or at or beyond Target 1. Setup 5 levels are option premiums and are not checked this way.
* **EOD square-off:** live positions still open at the square-off time exit at the cycle's bid (as other live exits do); the last traded price is used only when no bid is known.
* **Late Target 2 fill (live book, Setups 1-4 and the other spot-managed setups):** when spot touches Target 2 but no fresh option quote exists, the exit waits for the next quote (as before). If that quote is already below the option Target 2 level, the trade still exits but is recorded as `CLOSED` with reason `(Late Fill: ...)`, not as `TARGET_2`. Only the label changes; when and at what price the trade exits does not.
* **Feed lost with live positions open:** stops and targets are only checked while the Dhan feed is live. During the session, if the feed drops while live positions are open, a `live_positions_unmanaged` alert repeats every 10 minutes until the feed is back; the 15:20 square-off still runs.

### 3. Persistent SQLite Storage
* Realized trades, active positions, performance metrics, and processed signal IDs are committed atomically to SQLite (`data/trades.db`).
* **Portfolio reset** archives every row (hidden, not deleted) and is refused while a live-feed position or a routed broker position is open. Processed signal IDs and a daily loss cap tripped today survive a reset.
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
All three require "bands are wide": `BandWidth >= SNAPBACK_MIN_BW_RATIO (default 1.3) x BandWidth 20-bar minimum` (changed 2026-10-16: the old `BandWidth > SQUEEZE_ABS_BW_PCT` (5%) gate could not pass on 5m bars, so Setups 6-8 never fired; Setup 1 still uses `SQUEEZE_ABS_BW_PCT`). They use a 1-strike ITM strike, with targets at the 20 SMA (Target 1) and the opposite band (Target 2).

| Setup | Enum | Trigger (PE shown; CE is the mirror) |
|---|---|---|
| 6 | `SETUP_6_PINBAR_SNAPBACK` | `ADX <= 25`; high pierces the upper band, close back inside, upper wick >= 50% of the bar range, body in the lower 60%, `RSI >= 68`, close above the 20 SMA. SL above the pin-bar high. |
| 7 | `SETUP_7_INSIDE_BAR_SNAPBACK` | Bar t-2 reaches the 2.5σ band, bar t-1 is an inside bar, bar t closes below the inside bar's low, close above the 20 SMA. SL above the mother-bar high. |
| 8 | `SETUP_8_DIVERGENCE_SNAPBACK` | Climax swing with RSI divergence fading back toward the mean. Peak 1 pierces the upper band with `RSI >= 70`; peak 2 (last 3 bars) retests peak 1 within 0.2% with RSI at least **5** points lower; the trigger bar is bearish (`close < open`), closes back inside the band and above the 20 SMA. CE is the mirror (`RSI <= 30`). Tightened 2026-10-16 from RSI gap 2 and no RSI/candle filter, which fired on about 4% of random-walk bars. |

### 11.2 Setup 3: code follows section 4
Aligned on 2026-10-16 (from the Setup 3 analysis). Leg 1 is 5-20 bars back and must pierce the band; leg 2 is the lowest low of the last 5 bars, at least 3 bars after leg 1, inside the band and not more than 0.25 ATR(14) beyond leg 1; RSI divergence margin is 1.5 points; the trigger needs the neckline cross **and** close beyond the 9 EMA.

Setup 3 also waits for at least 20 bars of the current session (same rule as Setup 2), so the overnight gap does not distort the bands and RSI at the first low.

Stop-loss: second low (high for M) minus (plus) 0.1 ATR(14), replacing the flat 1.0 point under the deeper of both lows. The old stop gave about 1.3x the risk of the second-low stop in the synthetic run (median 62 vs 52 NIFTY points), so fewer lots and farther targets. The spec's flat 2.0 point buffer was dropped because it does not scale across NIFTY and stocks. Watch the first week of paper trades for extra wick stop-outs.

### 11.3 Stock ranking and risk cap
* The momentum ranker is constructed with `top_n = 10` in `scanner_worker.py` (the class default and section 7 say 5).
* The risk cap skips a trade when risk per lot exceeds **1×** the max risk cap (`paper_trader.py`), not 2× as section 8 states.

### 11.4 Changes made after this spec was written
* VWAP for instruments with no volume (cash indices) is the session-cumulative mean of typical price, not the single bar's typical price.
* RSI / ATR / DI / ADX use Wilder smoothing seeded with an SMA; ADX is undefined (neutral 20) before bar 28.
* "Squeeze" for Setup 1 uses `SQUEEZE_ABS_BW_PCT` (default 5.0 = legacy; nearly always true on 5m bars) and is unchanged. Setups 6-8 use their own `SNAPBACK_MIN_BW_RATIO`. Recalibrate with `scripts/compare_squeeze.py` on recorded candles.
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

## 13. Setup 10: ATM Straddle Premium Squeeze

* **Setup Enum:** `SetupType.SETUP_10_STRADDLE_SQUEEZE`; code in `backend/app/services/straddle_squeeze.py`, signal assembly shared with Setup 5 (`build_option_chart_signal`).
* **Underlying Principle:** Index options reprice on volatility before spot trends. A Bollinger squeeze on the combined ATM CE + ATM PE premium shows volatility compression that spot BandWidth can miss. When the combined premium then expands, the leg that leads the move is bought.

### Qualification (all on completed 5m bars)
1. **Straddle chart:** on the bars both ATM legs share, straddle OHLC = CE + PE (volume summed). Bollinger (20, 2.0), BandWidth and its 20-bar minimum are computed on that series. Needs 20 aligned bars today (so the first entry is about 11:00 IST) and both legs must have closed the same latest bar.
2. **Squeeze:** in at least one of the 3 bars before the trigger bar, straddle `BandWidth <= 1.30 x` its 20-bar minimum (the Setup 1 factor; the always-true absolute 5% rule is not used).
3. **Expansion:** the trigger bar's straddle close is above its upper band and above the previous straddle close.
4. **Direction:** the leg with the larger bar gain must gain at least 3% on the bar while the other leg does not gain. If both legs rise (a volatility spike) there is no trade.
5. **Leg confirmation:** the leading leg closes above its own session VWAP and 9 EMA, and its bar volume is real, at least 1,000 contracts and 1.2x its prior 20-bar average (same filter as Setup 5).
6. **Windows:** same entry cutoff (15:15) and expiry-day cutoff as Setup 5.

### Risk and management
* Strike: ATM, the bought leg only. Entry, stop (`max(close - 9 EMA, 0.5 x bar range, 4% of close)`), T1 1.5R and T2 2.5R are the Setup 5 premium formulas, and the position is managed on the option chart only (no spot checks), like Setup 5.
* Setup 5 and Setup 10 never enter the same side in one scan: when Setup 5 fires on a leg, the Setup 10 signal for that side is dropped.
* Default per-setup switch: `index` (NIFTY, BANKNIFTY, FINNIFTY, SENSEX, MIDCPNIFTY, NIFTYNXT50). Stock option premiums are too thin for a stable straddle series.
* The signal's indicator snapshot logs `straddle_close`, `straddle_bb_upper`, `straddle_bandwidth`, `straddle_bandwidth_20_min` and each leg's bar gain, so thresholds can be tuned from paper trades.

### Notes
* The thresholds (1.30x, 3 bars, 3% leg gain) are starting values. Option candles for past sessions are not available for replay, so this setup is validated by paper trading.
* The ATM strike can change during the day; each strike has its own full-day exchange series, so the straddle is always built from the current ATM pair.


---

## 14. Setup 11: removed (2026-10-19)

Setup 11 (filtered shadow of Setup 5) no longer generates signals: the module `setup11.py`, its scanner wiring and its dashboard filter tab were deleted. On 2026-10-19 it took 19 trades for -35,282 against Setup 5's -4,934 on 11 trades, and it traded signals Setup 5 itself was blocked from, so it was not a like-for-like comparison. See `notes/trade_loss_analysis_2026-10-19.md`.

Kept on purpose, so earlier trades still load and report: the `SETUP_11_FILTERED_OPTION_BB` enum value, `is_setup11`, and the separate Setup 11 loss pool for positions already in the database. Nothing new enters that pool.

## 15. Setup 12: ADX + EMA 20 Trend Cross

* **Setup Enum:** `SetupType.SETUP_12_ADX_EMA_CROSS`; code in `backend/app/services/setup12.py`, wired in `scanner_worker` next to Setup 9 (completed bars only).
* **Origin:** the TradingView "Trinity ADX + EMA Scalper" Pine script. Its raw signal is "close crosses the EMA 20 in the direction of the candle", which fires on every cross in chop. Here the script's optional ADX filter is always on, plus distance and time guards. Setups 1 and 5 are unchanged.
* **Underlying Principle:** take an EMA 20 cross only when a trend is already present (ADX at a trend level and rising, +DI/-DI aligned with the trade). Unlike Setup 2 it does not need a band walk or a 9 EMA pullback, so it can fire at the start of a trend leg.

### Qualification (CE shown; PE is the mirror), on completed 5m spot bars
1. **Cross:** previous close <= previous EMA 20 and close > EMA 20 (Pine `ta.crossover`), and close > previous close. EMA 20 is `close.ewm(span=20)`.
2. **ADX gate (always on):** ADX >= 20 (Pine "strong" level) and ADX > its value 3 bars earlier, and +DI > -DI (PE: -DI > +DI). ADX/DI are the engine's Wilder values (Section 1), not the script's plain 14-bar average, so numbers differ slightly from the Pine plot. ADX is neutral (20) until 28 bars exist, so it cannot rise before then.
3. **Distance:** close - EMA 20 must be between 0.1 and 1.0 ATR(14). Drops marginal crosses and chases.
4. **Window:** at least 20 bars of the current session (first entry about 10:55 IST) and bar start no later than 14:25 (signal confirms at 14:30). Needs at least 30 bars of history so ADX is real (not the neutral 20.0 warm-up fill); only evaluated on the 5m timeframe.

### Risk
* Stop: `min(EMA 20, bar low) - max(0.25 x bar range, 0.05% of close)` (PE mirrored), the Setup 2 formula on the 20 EMA. Targets T1 1.5R / T2 2.5R on spot, strike 1 ITM, partial booking at T1, sizing, risk cap and chop-box re-entry gate as for Setups 1 to 4.
* Default per-setup switch: `index`.

### Notes
* Thresholds (ADX 20, 3-bar rise, 0.1 to 1.0 ATR, 14:25 cutoff) are starting values chosen before any replay; tune them from paper trades. The Pine script's 8-bar highest/lowest close lines are plot-only and not used.
* Option fills, slippage and costs cannot be tested from past data (no past option candles). The spot signal can be replayed on past 5m index candles.
---

## 16. Runtime Settings, Entry Limits & Telemetry

Every limit below is a **runtime setting**: editable from the dashboard's Settings tab (or `PUT /api/settings`), validated, saved in the database, written to an audit trail (`settings_audit`) and applied to the next decision with no restart. A saved value wins; otherwise the environment default (`app/core/config.py`) applies. Definitions live in [`runtime_settings.py`](backend/app/services/runtime_settings.py).

### New entry limits (all apply to every setup in each book ; 0 switches a limit off)
| Setting | Effect |
|---|---|
| `max_lots_per_trade` | Hard ceiling on lots per entry, applied after the risk-based sizing in section 8. Default 0 (off). |
| `max_entries_per_day` | Most entries per book per IST day across all symbols. Default 0 (off). |
| `max_consecutive_losses` | After this many losing trades in a row today, new entries in that book pause until a winner closes or the next IST day. Default 0 (off). |

Existing limits are now runtime settings too, with the same defaults as before: `daily_loss_limit`, `max_open_positions`, `max_open_notional`, `max_entries_per_symbol_per_day`, `reentry_cooldown_seconds`, `default_lots`, `max_risk_per_trade`, `max_quote_age_seconds`, `max_entry_spread_pct`, `gap_exit_pct`.

### Entry liquidity gate (all setups, paper entries)

Applied after the setup has signalled and the strike is chosen, immediately before a paper position opens (`liquidity_filter.py`, called from `paper_trader.py`). It changes no setup rule: a signal is simply not entered when the option contract is too illiquid, and the skip is logged with reason code `LIQUIDITY_SKIP` (detail e.g. `spread 23.9% > 3%` or `OI 1200 < 5000`) so it shows in the skips list.

| Setting | Default | Effect |
|---|---|---|
| `liquidity_gate_enabled` | on | Master switch. Off keeps only the "would_skip" log line. |
| `liquidity_max_spread_pct` | 3 | Skip when (ask - bid) / ask is wider than this. 0 disables the check. |
| `liquidity_min_oi` | 5000 | Skip when the option's open interest is lower. 0 disables the check. |
| `liquidity_min_volume` | 100 | Skip when the option's day volume is lower. 0 disables the check. |

A quote field that is missing never triggers a skip. This replaces the earlier shadow-mode filter (`LIQ_FILTER_ENABLED`, default off); the `LIQ_*` environment values remain as the defaults. Basis: 15-19 Oct paper trades with spread above 5% had no winners (-19.4k) and contracts with OI below 5000 had no winners (-21.3k). **Setup 5:** its entry and exit rules are unchanged, but its option entries are subject to the gate like every other setup, so Setup 5 trades on wide or thin contracts are now skipped.

### Telemetry (no change to any setup rule)
* `strategy_decisions`: every ENTERED / SKIPPED / EXITED decision with a reason code (e.g. `MAX_OPEN_POSITIONS`, `SPREAD_TOO_WIDE`, `LOSS_CAP`, `SETUP_SWITCHED_OFF`) and the numbers behind it.
* `trade_excursions`: per trade MFE (best open profit) and MAE (worst open loss) in rupees, plus final P&L.
* `error_events`: warnings and errors from the app's loggers, grouped under a short code.
* `GET /api/telemetry/performance` reports expectancy, profit factor, drawdown, longest loss streak, MFE capture, by setup, symbol, entry hour and exit reason. Switches: `telemetry_enabled`, `telemetry_jsonl_enabled`, `telemetry_skip_logging`, `telemetry_retention_days`.

---

## 17. Stock Earnings Options (paper book)

A separate paper book (`earnings` in the decision trail), **paper only**, off by default (`earnings_enabled`). Code: [`earnings_strategy.py`](backend/app/services/earnings_strategy.py) (rules), [`earnings_engine.py`](backend/app/services/earnings_engine.py) (book, Dhan chain provider). Stocks, lot sizes and security ids come from `backend/app/data/fno_universe.json`; the earnings calendar (symbol, date, session BMO/AMC, sector) is filled once a day from the NSE event calendar (F&O stocks with a "Financial Results" board meeting within `earnings_sync_horizon_days`; `earnings_auto_sync` switches it off) and can also be entered or edited in the Earnings tab. NSE publishes no before-open / after-close flag, so the sync infers the session from any time of day or wording in the NSE event ("before market" or a time before 09:15 IST = BMO; "after market" or a later time = AMC); when NSE gives nothing usable the row stays empty and the default below applies. The Earnings tab shows for every row where its session comes from: manual, inferred, default or skip. A session you pick on a row (manual) always wins over inference and the default and is never replaced by the sync. Rows you add or edit are never overwritten or removed by the sync; NSE rows that NSE moves or drops are updated. Every number below is a runtime setting (`earnings_*`).

**Timing.** The market reacts on the announcement day for BMO (before open) and on the next trading day for AMC (after close) or a non-trading date. The last safe close is the trading day before the reaction day. Calendar rows with no session follow `earnings_default_session` (default AMC, since most Indian results come after the close; AMC is also the more cautious reading as it moves the last safe close to the result day; set SKIP to not trade unset rows).

**Mode A, pre-earnings run-up (long ATM straddle).**
* Entry: earnings between `earnings_mode_a_near_days` and `earnings_mode_a_far_days` calendar days away (default 8 to 12), after `earnings_entry_time`; ATM strike from the live chain; bought at the ask. Refused when IV percentile is above `earnings_mode_a_max_ivp` (default 40, 0 = off; needs `earnings_iv_min_history` days of stored IV, else `earnings_iv_missing_policy`), when a leg's spread exceeds `earnings_max_spread_pct`, or when premium exceeds `earnings_max_capital_per_trade`.
* Expiry: the earliest listed expiry at least `earnings_min_days_to_expiry` days after the exit date (rolls to the next expiry automatically).
* Exit, first to fire: loss of `earnings_mode_a_max_loss_pct` of the premium (default 40, 0 = off); expiry closer than the minimum; scheduled exit `earnings_mode_a_exit_days_before` trading days before the last safe close, at `earnings_exit_time`.

**Mode B, post-earnings IV crush (defined-risk iron condor).**
* Entry: on the last safe close day; short strikes `earnings_condor_short_steps` grid steps from ATM, wings `earnings_condor_wing_steps` beyond; shorts sold at the bid, wings bought at the ask. Refused when net credit is at or below `earnings_min_condor_credit`, IV rank is below `earnings_mode_b_min_ivr` (default 0 = off), spreads are too wide, or max risk exceeds the capital cap.
* Exit, first to fire: spot at or beyond either short strike; expiry closer than the minimum; reaction day at `earnings_mode_b_exit_time`.

**Risk gates (every entry).** Kill switch, daily loss limit, consecutive-loss pause, `max_entries_per_day`, `max_open_notional` (on max risk), `earnings_max_positions`, one position per sector (`earnings_one_per_sector`), one position per stock, lots = `earnings_lots` capped by `max_lots_per_trade`. The kill switch also squares off this book. Positions are never entered or exited on a quote that could not be refreshed; a scheduled exit more than a day overdue closes at the last known prices.

**Costs.** Charges per leg use the same calculator as the other setups.



---

## 18. Setup 13: Option VWAP Reclaim

* **Setup Enum:** `SetupType.SETUP_13_OPTION_VWAP_RECLAIM`; code in `backend/app/services/setup13.py`, wired in `scanner_worker._evaluate_option_chart_setups`; signal assembly shared with Setups 5 and 10 (`build_option_chart_signal`, with an optional `stop_price` that Setups 5 and 10 do not pass, so their stops are unchanged).
* **Underlying Principle:** VWAP of the option's own premium is the average price its buyers paid today. A premium above it means buyers are in profit; a dip below it and a close back above it means buyers have retaken control. Buying that reclaim enters a pullback inside an existing trend at a level many traders watch, instead of chasing a spike (Setup 5 buys the spike).

### Qualification (CE shown; PE is the same on the put's own premium), all on completed 5m bars
1. **Prior trend:** the bar before the dip closed above the option's session VWAP.
2. **Dip:** 1 to 5 consecutive bars immediately before the signal bar closed below VWAP (a longer dip is a failed trend; no dip is not a pullback).
3. **Reclaim:** the signal bar closes above the option's session VWAP (the Section 1 VWAP of the option chart).
4. **Volume lift:** per-bar volume of the signal bar is at least 1,000 contracts and above the average of the prior 3 bars. Option volume from the feed is cumulative for the day; the scanner turns it into per-bar volume (difference of day totals) and flags bars where that is unknown (`volume_known=False`), which never pass.
5. **Spot agrees:** the underlying's completed bar at the same time closes above its own VWAP for calls, below it for puts. For an index the spot VWAP is the session mean of typical price (indices have no volume, Section 1).
6. **Window:** at least 6 bars of the current session on the option chart (first entry about 09:45 IST; VWAP restarts every session, so earlier days' bars cannot help it and are not counted), bar start no later than 14:25 (confirms at 14:30), plus the shared option-chart guards (today's bar only, entry cutoff, expiry-day cutoff).

### Risk and management
* Strike: ATM, the bought leg only; entry is the signal close. Stop: `max(pullback low, VWAP) - 1% of the close`, never tighter than 4% of the close; the signal is skipped if the stop would be more than 30% below the close. T1 1.5R (book half, stop to breakeven), T2 2.5R, sizing, caps and the option-chart-only exits are the Setup 5 ones.
* Setup 13 never enters the same side as Setup 5 or Setup 10 in one scan.
* Default per-setup switch: `index`. Stock option premiums are too thin for a stable VWAP.
* The signal's indicator snapshot logs `dip_bars`, `pullback_low`, `volume_avg_prior_3`, `spot_close` and `spot_vwap` so thresholds can be tuned from paper trades.

### Notes
* Thresholds (6-bar warm-up, 1 to 5 dip bars, 3-bar volume average, 1,000 contracts, 1% stop buffer, 30% stop cap, 14:25 cutoff) are starting values. Past option candles are not available for replay, so this setup is validated by paper trading.

---

## 19. Setup 14: PCR / OI Wall Bounce

* **Setup Enum:** `SetupType.SETUP_14_OI_WALL_BOUNCE`; code in `backend/app/services/setup14.py`, wired in `scanner_worker` right after the option chain is fetched (before live strike enrichment). Signal is on the underlying (like Setups 1-4 and 12); the traded leg is picked by the usual strike selector.
* **Underlying Principle:** open interest (OI) in the option chain shows where large positions sit. The strike with the most put OI below spot tends to act as support (writers defend it) and the strike with the most call OI above spot as resistance. The setup buys the first rejection of such a wall, so the stop is close and the level is clear.
* **Data:** Dhan `/optionchain` `oi` field per strike and side. The scanner already caches the nearest-expiry chain with a 15 s TTL, so no extra API calls are made. Exchange OI itself moves slowly (it is not tick data), which is why walls are recomputed every 15 minutes, not every cycle. A signal is skipped when the chain behind the walls is older than 120 s. Chain freshness could not be measured against the live API from the build environment, so the first sessions should be checked through the `chain_age_s` and OI fields in the signal snapshot.

### Walls and bias
1. **Wall:** the strike with the largest put OI at or below spot (support) or the largest call OI at or above spot (resistance), within 5% of spot, and only if its OI is at least 1.5x the OI of each adjacent strike (otherwise there is no wall on that side). A chain with no OI returns no walls.
2. **PCR:** total put OI divided by total call OI across the fetched chain. Calls at support need PCR >= 1.2; puts at resistance need PCR <= 0.8; in between the day is skipped.
3. Walls and PCR are recomputed every 15 minutes (`WALL_REFRESH_S`) and reset each session.

### Qualification (CE at support shown; PE at resistance is the mirror), on completed 5m spot bars
1. The bar's low reaches within 0.1 ATR of the wall strike (or through it).
2. The bar closes back above the wall (PE: below), and no more than 1.0 ATR away from it (no chasing).
3. Lower wick (PE: upper wick) at least as long as the body.
4. First touch: no earlier completed bar of today reached within 0.1 ATR of the same wall.
5. At least 3 bars of the session; bar start no later than 14:25 (confirms at 14:30).

### Risk and management
* Entry: signal close. Stop: the tighter of the wall strike and the candle extreme, with a buffer of max(0.1 ATR, 0.03% of price); the strike selector enforces its usual minimum stop distance. T1 1.5R (book half, stop to breakeven), T2 2.5R, sizing, caps, re-entry gate and exits are the Setups 1-4 ones. The opposite wall is logged in the snapshot (`opposite_wall`) but is not used as a target.
* Default per-setup switch: `index` (stock chains are thin and walls are noisy).
* Snapshot logs `wall_strike`, `wall_oi`, `wall_oi_ratio`, `pcr`, `opposite_wall`, `opposite_wall_oi`, `wick`, `body`, `chain_age_s`. The snapshot holds numbers only: when a value has no wall (typically `opposite_wall` / `opposite_wall_oi` on the far side of price) the key is omitted instead of set to null. (Fixed 2026-10-19: null values failed signal validation and silently dropped valid bounces. Entry logic is unchanged.)

### Notes
* Thresholds (1.5x dominance, 5% range, PCR 1.2 / 0.8, 0.1 ATR touch, 15-minute refresh, 120 s chain age) are starting values chosen before any replay. Past option-chain OI is not stored, so the setup can only be validated by paper trading; store signal snapshots to tune it.
* It fits expiry week best and is expected to fire only a few times a day. A broken wall can flip into a fast trend, so the stop is firm.
* Setups 1 and 5 are unchanged.

---

## 20. Setup 15: ATR Trend Flip (swing equity book)

* **Book:** `swing` in the decision trail. A separate **paper-only, long-only, cash-delivery** book on **daily bars**, off by default (`swing_enabled`; Setup 15 itself has `swing_setup15_enabled`). It is not an option setup and does not use the per-setup switches or the intraday scanner. Code: [`swing_signals.py`](backend/app/services/swing_signals.py) (Supertrend and filters, pure), [`swing_engine.py`](backend/app/services/swing_engine.py) (book, Dhan daily provider), [`swing_report.py`](backend/app/services/swing_report.py) and [`scripts/swing_backtest.py`](backend/scripts/swing_backtest.py) (replay). Universe: the F&O stocks in `app/data/fno_universe.json`. Every number below is a runtime setting (`swing_*`, Settings tab).
* **Underlying principle:** a Supertrend (ATR bands that only tighten toward price) flips from down to up when price closes through the upper band, i.e. a new uptrend starts; the lower band then trails as the stop. It has a low hit rate and relies on winners being larger than losers. It is the only family with swing-horizon NSE numbers in the research (`reports/Indian swing equity strategies.md`: Nifty 500, 2012-2025, ATR 3 / multiplier 1, about 41% wins, average win about 2.3x average loss, about 15 days); that study was a broker blog without costs, taxes or survivorship control, so this setup is a **hypothesis to be tested by `scripts/swing_backtest.py` and paper trading**, not a proven edge.
* **Data:** daily candles from Dhan `POST /charts/historical`, cached in `swing_daily_bars` (first fetch about 560 calendar days, then incremental). Dhan does not document whether history is adjusted for splits and bonuses: check one known split date before trusting a backtest.

### Signal (on the last finished daily bar, nothing later is read)
1. Supertrend(`swing_atr_period` = 3, `swing_atr_mult` = 1.0) on high/low/close, Wilder ATR, computed on the last 200 bars; trend flips from down to up on this bar.
2. Close above its `swing_sma_filter_days` (200) simple average (0 turns it off).
3. Close at least `swing_min_price` (50) and 20-day average volume at least `swing_min_avg_volume` (100,000).
4. Stop = the Supertrend line on the signal bar (below the close). Candidates are ranked by 63-day return when more flips occur than free slots (an untested tie-break).

### Entry
* Queued at the close, filled at the **next trading day's open plus `swing_slippage_bps`** (10). A fill is cancelled if the open is already at or below the stop (`GAP_THROUGH_STOP`) or if the size rounds to under one share.
* Quantity = `swing_risk_per_trade` (5,000) / (entry - stop), capped by `swing_max_capital_per_trade` (100,000) / entry.
* **Gates (at the close that queues it):** swing book and Setup 15 enabled, kill switch not engaged, one position per stock, `swing_max_positions` (5) open or queued, `swing_max_new_per_day` (3) per close, and no results inside `swing_earnings_blackout_days` (5; uses the earnings calendar).

### Exit (stops win ties; gaps fill at the open)
* **Exit mode `stop` (default):** the trailing Supertrend line is a stop order. A bar whose low reaches it exits at the stop; an open at or below it exits at the open (`STOP_GAP`). The stop only ratchets up.
* **Exit mode `close`:** the line only triggers an exit at the **next open** after a close beyond it (`TREND_FLIP`), as the Indian study did; inside a day only the max-loss stop (`swing_close_mode_max_loss_pct`, 8% below entry) protects the position, and sizing uses the smaller of the line distance and that stop.
* **Time stop:** at the next open after `swing_max_hold_days` (20) trading days. Kill switch: open positions close at the last close, queued entries are cancelled.
* **Costs:** `calculate_equity_delivery_charges`: STT 0.1% each side, NSE fee 0.00307%, SEBI Rs 10/crore, stamp 0.015% on the buy, GST 18% on brokerage and fees, DP Rs 15.34 per sell day (`swing_dp_charge`), brokerage `swing_brokerage_per_order` (0: unverified for Dhan). About 0.24% of the position value round trip, before slippage.

### Operation
* `run_cycle` runs every `swing_poll_seconds` (600); after `swing_scan_time` (16:00 IST) on a trading day it fetches the finished bars, processes each missed trading day (at most 30, so stops on missed days are still checked) in order and scans only the latest. Days count as available once half the requested symbols have their bar. The first run starts today, with no replay of the past. Open positions are always managed even when the book is switched off.
* Endpoints: `GET /swing/summary`, `/positions`, `/candidates` (signals on the latest bar, nothing queued), `POST /swing/run`. The deploy gate (`deploy/vm/bb-deploy.sh`) counts OPEN and PENDING swing rows.
* Replay: `python -m scripts.swing_backtest DATA_DIR` runs the production engine over per-symbol daily CSVs and reports trades, win rate with a Wilson interval, expectancy in R with a bootstrap interval, profit factor, drawdown, a walk-forward split and a double-slippage run. Under 100 trades it says so. The symbol list given is survivor-biased if it is today's F&O list.

### Notes
* With the stop on the Supertrend line, the close that flips the trend has already traded through the stop that day, so in `stop` mode `TREND_FLIP` exits only appear as a safety net. `stop` and `close` modes should both be replayed: the study's numbers belong to `close`.
* Defaults (3 / 1.0, 200-day filter, 20-day time stop, 10 bps slippage) are starting values from that single study, not optimised. Setups 1 and 5 are unchanged.

---

## 21. Setup 16: Option Squeeze Breakout

* **Setup Enum:** `SetupType.SETUP_16_OPTION_SQUEEZE_BREAK`; code in `backend/app/services/setup16.py`, wired in `scanner_worker._evaluate_option_chart_setups`; signal assembly shared with Setups 5, 10 and 13 (`build_option_chart_signal` with the optional `stop_price`; Setups 1 and 5 are unchanged). **Paper only, default per-setup switch: `off`** (turn it on to `index` or `all` in Settings).
* **Underlying principle:** a close above the option premium's own upper Bollinger Band is a momentum breakout, but it is only an early entry when the bands were tight just before it. After the bands have already expanded the same close is a late chase and the lower band is far below the price. So the setup asks for a squeeze first and takes the nearer of the lower band and a percentage as the stop.

### Qualification (CE shown; PE is the same on the put's own premium), on completed 5m option bars
1. **Bands of the current session only:** upper and lower band = 20-bar mean of closes ± 2 standard deviations, with at least 12 closes of the signal bar's session (first entry about 10:00 IST). The option's previous day is a different price level and is not mixed in (Setup 5 uses the plain indicator columns).
2. **Breakout:** the signal bar closes above the upper band and closes above its own open.
3. **Squeeze just before:** the lowest BandWidth among the 6 bars before the signal bar is at most 1.30 times the lowest BandWidth the session has shown (the Setup 1 and 10 factor), and the signal bar's BandWidth is higher than the previous bar's.
4. **Volume:** per-bar volume at least 1,000 contracts and known (`volume_known` not False).
5. **Window (runtime settings):** bar start between `setup16_window_start` (09:30) and `setup16_window_end` (14:25), plus the shared option-chart guards (today's bar only, entry cutoff, expiry-day cutoff). Mid-morning entries (10:00 to 11:30) lost on 2026-10-19 across other setups; the window is a setting so it can be narrowed without a release.

No VWAP, RSI or volume-surge test (those are Setup 5's filters).

### Which stocks are checked
* Indices and the momentum top-10 bullish / top-10 bearish stocks plus stocks with an open position, like Setups 5, 10 and 13 (every stock's ATM CE and PE are checked; the ranker's bullish or bearish label is not used to pick the side).
* **After-close watchlist (`backend/app/services/watchlist.py`, runtime settings `watchlist_*`):** the list is built from the finished daily bars, after `watchlist_build_time` (16:15 IST) on a trading day, for the next trading day. It does not depend on a login at that exact time: the service polls every 10 minutes and builds as soon as a Dhan session exists and the list for the target day is missing, so a late-evening login still gets one. A login or restart before the close (or on a weekend or holiday) builds the list for the next session from the bars already stored. The F&O stocks are screened on their own **daily** charts (Dhan daily candles, shared with the swing book's cache): daily BandWidth (20, 2) within the lowest `watchlist_bw_percentile` (20%) of its last 120 days, or an NR7 day (`watchlist_use_nr7`), and a 20-day average traded value (close x volume) of at least `watchlist_min_avg_value_cr` (50 crore) as a liquidity proxy for the stock's options. The tightest `watchlist_size` (40) are saved to `watchlist.json` for the next trading day only (never reused when stale). The next day the scanner checks those stocks for **Setup 16 only**: the other setups never see them, they get no spot-chart seeding, and only Setup 16 signals survive. Being on the list never opens a trade; the setup rules and the per-setup switch decide. The **Setup 16 tab** shows the watchlist panel (when it was built, for which day, the stocks and why each qualified, a "Check now" button). `GET /api/watchlist` shows the list, `POST /api/watchlist/run` rebuilds it (still only after the build time).
* The daily-squeeze screen is a hypothesis: a daily squeeze improving next-day option breakouts is untested here.

### The Setup 16 tab (what is happening)
`GET /api/setup16/overview`, refreshed every 10 seconds by the dashboard tab: the per-setup switch state and settings (entry window, stop %); a funnel counting every checked option chart by where it stands (signal, below the upper band, broke out with no squeeze before, red bar, volume too low, outside the window, warming up, no data); the contracts closest to a breakout (close, upper band, distance, squeezed or wide, checked-at time, "WL" for watchlist stocks; a contract not re-checked for 15 minutes is dimmed); open and today's closed Setup 16 positions with net P&L and all-time stats; the watchlist; and the last 24 hours of Setup 16 entries and skips from the telemetry trail (for example `SETUP_OFF`). The stage and numbers come from the `diag` argument of `evaluate_option_squeeze_breakout`; the scanner keeps the latest one per contract in memory (not persisted).

### Risk and management
* Strike: ATM, the bought leg only; entry is the signal close. **Stop = the nearer (higher) of the option's lower band and `setup16_stop_pct` (12%) below the close**, never tighter than the 4% minimum of the shared builder. The stop is a price level checked against the live premium like every option-chart setup, not a wait for a bar to close below the band. T1 1.5R (book half, stop to breakeven), T2 2.5R, sizing (8,000 max risk per trade), caps and option-chart-only exits are the Setup 5 ones.
* **Overlap with Setup 5:** Setup 5 is the same band-break entry with extra filters (VWAP, RSI >= 58, volume surge), so most of its signals would also qualify here unless the squeeze test fails. To avoid two entries on one contract, Setup 16 is dropped when Setup 5, Setup 10 or Setup 13 has already fired on the same side in the scan. Its own entries are the breakouts Setup 5 rejects on RSI, VWAP or volume surge, after a squeeze.
* The signal's indicator snapshot logs `squeeze_bw_min`, `session_bw_min`, `breakout_bw`, `lower_bb` and `stop_is_lower_bb` so the squeeze factor and the stop percentage can be tuned from paper trades.

### Notes
* Thresholds (12-bar warm-up, 6-bar squeeze lookback, 1.30 factor, 1,000 contracts, 12% stop, 09:30 to 14:25 window) are starting values. **Not replayed on real option candles** (none were available when it was written); it is validated by paper trading. The market recorder (`market_bars.db`) keeps completed option bars, so a replay becomes possible after a few sessions.

## 22. Commodities & Currency book: Setups 17, 18 and 19

A separate **paper** book for MCX commodity options and NSE currency options. It never touches the NSE index / stock scanner, the NSE loss cap or live broker routing. **Off by default** (`cx_enabled`); each pool and each setup also has its own switch (Settings → Commodities & Currency book).

* **Code:** `backend/app/services/cx_signals.py` (the three setups), `cx_engine.py` (positions, entries, exits, pools), `cx_instruments.py` (underlyings, live contract lookup), `exchange_sessions.py` (MCX and currency hours), `charges_calculator.py` (`calculate_mcx_option_charges`, `calculate_currency_option_charges`), API `backend/app/api/cx.py` (`/api/cx/overview`, `/summary`, `/positions`, `/candidates`, `/run`), tab "Commodities & FX" (`CxScreen.tsx`).
* **Underlyings (start):** CRUDEOIL and GOLDM on MCX (pool `commodity`), USDINR on NSE currency (pool `currency`). Each option is written on the **live futures contract**, which rolls monthly: security ids, lot sizes and expiries are read from Dhan's instrument master (`cx_instruments.nearest_futures`, cached once a day in `data/cx_contracts.json`), never hardcoded. An unknown lot size refuses the entry. GOLDM is quoted per 10 g but a lot is 100 g, so P&L uses `lot size / quote unit` (`CxUnderlying.quote_unit`); verify this with the Phase 0 check before trusting GOLDM P&L.
* **Data:** 5-minute candles of the future (`/charts/intraday`, instrument FUTCOM or FUTCUR); the option chain of the first option expiry **after today** (`/optionchain`), which supplies the bid, ask and strike list. The bar still forming is dropped. If the last completed bar is older than 20 minutes during a session the underlying is skipped (`STALE_DATA`).
* **Sessions (`exchange_sessions.py`, settings `cx_mcx_*`, `cx_cur_*`):** MCX Mon-Fri 09:00-23:30 IST (23:55 in US daylight saving: change `cx_mcx_close`), last entry 22:30, square-off 23:15. NSE currency Mon-Fri 09:00-17:00, last entry 16:15, square-off 16:50. On an NSE holiday MCX runs the evening session only (from 17:00) unless the date is in `MCX_FULL_CLOSED`; currency is closed on NSE holidays. A year with no holiday data is treated as closed (same rule as NSE). `MCX_FULL_CLOSED` is a best-effort 2026 list to confirm against the MCX circular.

### Setup 17: range break with trend (`SETUP_17_RANGE_BREAK`)
On the last completed 5m bar: close above the highest high (below the lowest low) of the prior `cx_donchian_len` (20) bars, the previous bar had **not** already closed beyond its own prior range (fires on the break bar only), ADX >= `cx_adx_min` (20), +DI > -DI (or -DI > +DI), and the close on the right side of the 50 EMA. Buy CE (up) or PE (down). Invalidation level = the broken range edge minus (plus) 0.5 ATR.

### Setup 18: opening range break (`SETUP_18_OPENING_RANGE`)
The high/low of the first `cx_orb_minutes` (30) of the session window (09:00, or 17:00 on an MCX evening-only day). After the range is complete, the **first** bar to close beyond it (and only if no earlier bar closed beyond either side) buys CE (above) or PE (below). Invalidation level = the midpoint of the opening range.

### Setup 19: band fade in a range (`SETUP_19_BAND_FADE`)
ADX on the stretch bar <= `cx_adx_max_fade` (22). The stretch bar closes outside the Bollinger Band (20, 2) with RSI <= `cx_rsi_low` (30) below the lower band, or >= `cx_rsi_high` (70) above the upper band; the next bar closes back inside the band in the reversing direction (green after a lower-band stretch, red after an upper-band one). Buy CE after a downside stretch, PE after an upside one. Invalidation level = the stretch bar's low (high). The bet is a move back toward the 20 SMA.

### Entry, exit and risk (shared by the three setups)
* **Strike:** the at-the-money strike (nearest to the signal close) that has the leg; only the bought leg. Entry = ask x (1 + `cx_slippage_pct`). Skipped when there is no two-sided quote, the spread is wider than `cx_max_spread_pct` (15% of mid), the ask is below `cx_min_premium_commodity` (5) / `cx_min_premium_currency` (0.05), or the lot size is unknown. `cx_lots` (1) lots per trade.
* **Exits:** premium stop `cx_sl_pct` (30% below entry) and target `cx_target_pct` (50% above), both on the bid; time stop `cx_max_hold_minutes` (90); `INVALIDATED` when the future's last completed close is through the setup's level; exchange square-off time; kill switch. Positions are paper and persisted in `cx_positions`, so a restart keeps them.
* **Gates:** book / pool / setup switches, kill switch, exchange entry window, **pool daily loss cap** (`cx_loss_cap_commodity` 15,000 INR and `cx_loss_cap_currency` 5,000 INR, each pool separate and separate from every NSE book; net of estimated exit charges, open positions marked on the bid), one position per underlying, `cx_max_open_positions` (3), `cx_max_entries_per_symbol` (3 a day), `cx_cooldown_minutes` (15). One signal per bar per setup per underlying is acted on.
* **Charges:** MCX options: flat brokerage, CTT 0.05% on the sell premium, MCX transaction charge 0.0418%, SEBI fee, stamp duty, GST. Currency options: no STT/CTT, NSE transaction charge 0.035%. Rates are best-effort constants to confirm against the Dhan schedule.
* **Deploy:** `bb-deploy.sh` also refuses to deploy while a `cx_positions` row is `OPEN`. The evening sessions mean "after 15:30 IST" is no longer enough to be idle, so the open-position check is what protects a Commodities & Currency position.

### Notes
* All thresholds are starting values, **not replayed on real MCX or currency candles** (none were available when written); the book is validated by paper trading and by the Phase 0 data check (`backend/scripts/check_mcx_currency_data.py`), which confirms that the Dhan account returns the instrument master, quotes, option chains with greeks, 5m candles and WebSocket packets for these segments.
* Slippage and spreads are tuned for NSE index options; MCX and currency option spreads differ, so paper results will flatter until `cx_slippage_pct` and `cx_max_spread_pct` are calibrated from paper fills.
* Premium units: MCX premiums are INR per quoted unit (barrel, 10 g), currency premiums INR per USD. A CRUDEOIL lot is 100 barrels, so one lot moves much more per rupee than an NSE option lot.
