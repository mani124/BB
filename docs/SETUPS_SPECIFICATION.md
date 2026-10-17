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

## 14. Setup 11: Filtered Option Chart Scalper (Setup 5 shadow)

* **Setup Enum:** `SetupType.SETUP_11_FILTERED_OPTION_BB`; code in `backend/app/services/setup11.py`, wired in `scanner_worker._evaluate_option_chart_setups`.
* **Why it exists:** the 2026-10-16 review (`notes/trade_loss_analysis_2026-10-16.md`) found Setup 5 lost 19,925 on 26 trades, with entry slippage and wide stops the largest costs. Setups 1 and 5 are not to be changed, so Setup 11 runs next to Setup 5 and the two are compared on the same days.

### Qualification
Setup 11 only sees Setup 5 signals. A Setup 5 signal becomes a Setup 11 signal when all three filters, read from the same option premium chart (completed bars), pass:
1. **Option trend strength:** the signal bar's RSI and BandWidth are both strictly higher than on the previous bar.
2. **Candle quality:** the signal bar is green (close above open) and closes in the top 60% of its high-low range (upper wick at most 40% of the range).
3. **Stop-width cap:** (fill - stop) / fill is at most 30%, where fill is the live ask when known and higher than the signal close, otherwise the signal close.

Entry, stop, T1 (1.5R), T2 (2.5R), sizing and the option-chart-only exits are identical to Setup 5. A skipped Setup 5 signal is logged as `Setup 11 skipped <symbol> <side>: <filter reason>`.

### Isolation from Setup 5
* Setup 11 trades as its own position even on the same contract as an open Setup 5 position (the duplicate is intended, so the two can be compared).
* Setup 11 has its own exposure caps (one position per contract and per symbol+side, max open positions, open premium notional, entries per symbol per day, re-entry cooldown and chop-box gate), counted only against Setup 11 positions, and Setup 11 positions are not counted against the other setups' caps.
* Setup 11 has its own daily loss cap (`DAILY_LOSS_LIMIT`, latched under `<book>:s11`); its P&L does not count toward the main cap. The kill switch applies to all setups.
* Default per-setup switch: `all`.

### Notes
* Filter thresholds (60% candle position, 30% stop width, strictly rising RSI and BandWidth) are starting values from one session; tune them from paper trades.
* Not included on purpose: an entry-time cutoff, an entry-slippage guard, spread/volume/OI limits and a stock-trend check. The 2026-10-16 data did not support the spread and volume limits, and a stock-trend check would bring a spot signal into a setup that reads only the option chart.


---

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

## 16. Setup 13: Option VWAP Reclaim

* **Setup Enum:** `SetupType.SETUP_13_OPTION_VWAP_RECLAIM`; code in `backend/app/services/setup13.py`, wired in `scanner_worker._evaluate_option_chart_setups`; signal assembly shared with Setups 5, 10 and 11 (`build_option_chart_signal`, with an optional `stop_price` that Setups 5, 10 and 11 do not pass, so their stops are unchanged).
* **Underlying Principle:** VWAP of the option's own premium is the average price its buyers paid today. A premium above it means buyers are in profit; a dip below it and a close back above it means buyers have retaken control. Buying that reclaim enters a pullback inside an existing trend at a level many traders watch, instead of chasing a spike (Setup 5 buys the spike).

### Qualification (CE shown; PE is the same on the put's own premium), all on completed 5m bars
1. **Prior trend:** the bar before the dip closed above the option's session VWAP.
2. **Dip:** 1 to 5 consecutive bars immediately before the signal bar closed below VWAP (a longer dip is a failed trend; no dip is not a pullback).
3. **Reclaim:** the signal bar closes above the option's session VWAP (the Section 1 VWAP of the option chart).
4. **Volume lift:** per-bar volume of the signal bar is at least 1,000 contracts and above the average of the prior 3 bars. Option volume from the feed is cumulative for the day; the scanner turns it into per-bar volume (difference of day totals) and flags bars where that is unknown (`volume_known=False`), which never pass.
5. **Spot agrees:** the underlying's completed bar at the same time closes above its own VWAP for calls, below it for puts. For an index the spot VWAP is the session mean of typical price (indices have no volume, Section 1).
6. **Window:** at least 20 bars of the current session on the option chart (first entry about 10:55 IST), bar start no later than 14:25 (confirms at 14:30), plus the shared option-chart guards (today's bar only, entry cutoff, expiry-day cutoff).

### Risk and management
* Strike: ATM, the bought leg only; entry is the signal close. Stop: `max(pullback low, VWAP) - 1% of the close`, never tighter than 4% of the close; the signal is skipped if the stop would be more than 30% below the close. T1 1.5R (book half, stop to breakeven), T2 2.5R, sizing, caps and the option-chart-only exits are the Setup 5 ones.
* Setup 13 never enters the same side as Setup 5 or Setup 10 in one scan.
* Default per-setup switch: `index`. Stock option premiums are too thin for a stable VWAP.
* The signal's indicator snapshot logs `dip_bars`, `pullback_low`, `volume_avg_prior_3`, `spot_close` and `spot_vwap` so thresholds can be tuned from paper trades.

### Notes
* Thresholds (1 to 5 dip bars, 3-bar volume average, 1,000 contracts, 1% stop buffer, 30% stop cap, 14:25 cutoff) are starting values. Past option candles are not available for replay, so this setup is validated by paper trading.
* Setups 1 and 5 are unchanged.
