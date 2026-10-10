# Design Specification: Mean-Reversion 20-SMA Snapback Strategies (Setups 6, 7 & 8)

## 1. Overview & Business Objectives
In addition to the existing momentum, trend-following, and reversal setups (Setups 1–5), traders frequently encounter overextended market conditions where price stretches violently beyond standard Bollinger Bands before snapping back to the 20-period Simple Moving Average (20-SMA) baseline.

This design introduces three distinct, separately tracked Mean-Reversion 20-SMA Snapback strategies:
- **Setup 6: Rejection Pin Bar Exhaustion Snapback** (Single-candle exhaustion with long rejection shadows, RSI overbought/oversold, and ADX non-trend filter)
- **Setup 7: Extreme 2.5σ Band Puncture & Inside Bar Breakdown** (Outer $2.5\sigma$ volatility envelope puncture followed by an Inside Bar compression and break)
- **Setup 8: Climax Swing RSI Divergence Fade** (Early sniper entry on secondary swing test with RSI divergence without waiting for lagging neckline breaks)

Each setup is independently identified, assigned dedicated setup enum types, mapped to ATM/1-strike ITM option contracts, tracked in the paper trading journal, and filterable in the frontend dashboard.

---

## 2. Technical Architecture & Strategy Rules

```
                      +------------------------------------------------+
                      |         5-Minute Intraday Candle Stream        |
                      +------------------------------------------------+
                                              │
                      ▼────────────────────────────────────────────────▼
                      |   Indicator Engine (app/services/indicators.py)|
                      |   • 20-SMA Midline, 2.0σ Bands, 2.5σ Bands     |
                      |   • RSI(14), ADX(14), %B, BandWidth, VWAP      |
                      +────────────────────────────────────────────────+
                                              │
             ┌────────────────────────────────┼────────────────────────────────┐
             ▼                                ▼                                ▼
  [Setup 6: Pin Bar Snapback]     [Setup 7: 2.5σ Inside Bar]     [Setup 8: Climax Divergence]
  • High/Low pierces 2.0σ band    • High/Low pierces 2.5σ band   • Swing 1 outside 2.0σ band
  • Rejection wick ≥ 50% range    • Next bar is Inside Bar       • Swing 2 tests with RSI div
  • Closes back inside band       • Trigger: Break Inside Bar    • Trigger: Close back inside
  • Guards: ADX < 25, RSI >70/<30 • Target: 20-SMA               • Target: 20-SMA
             │                                │                                │
             └────────────────────────────────┼────────────────────────────────┘
                                              ▼
                      +------------------------------------------------+
                      | Strike Selector (ATM / 1-Strike ITM: Delta 0.52)|
                      +------------------------------------------------+
                                              │
                      ▼────────────────────────────────────────────────▼
                      | Paper Trader Execution (Slippage + Tax Engine) |
                      | Frontend Setup Filter & Dynamic Performance    |
                      +------------------------------------------------+
```

### 2.1 Indicators Computation Extensions
In `backend/app/services/indicators.py`:
- Standard deviation calculation:
  $$\sigma = \text{std\_dev}(close, 20)$$
- Extreme $2.5\sigma$ Bands:
  $$bb\_upper_{2.5} = bb\_middle + 2.5 \times \sigma$$
  $$bb\_lower_{2.5} = bb\_middle - 2.5 \times \sigma$$
- Add `bb_upper_25` and `bb_lower_25` to indicator output dataframe.

---

### 2.2 Setup 6: Rejection Pin Bar Exhaustion Snapback
- **Timeframe**: 5m candles.
- **Direction & Triggers**:
  - **Bearish PE Entry**:
    - Candle high pokes above Upper Band ($high > bb\_upper$).
    - Rejection upper wick $\ge 50\%$ of candle range:
      $$(high - \max(open, close)) \ge 0.50 \times (high - low)$$
    - Close falls back strictly inside Upper Band ($close < bb\_upper$).
    - Candle body is in lower half: $\max(open, close) \le (low + 0.60 \times (high - low))$.
    - **Guards**:
      - $RSI \ge 68.0$ (overbought exhaustion).
      - $ADX \le 25.0$ (guarantees market is NOT in a runaway directional trend).
      - $Bandwidth > 5.0$ (ensures sufficient point spread to 20-SMA for profitable R:R).
  - **Bullish CE Entry**:
    - Candle low pokes below Lower Band ($low < bb\_lower$).
    - Rejection lower wick $\ge 50\%$ of candle range:
      $$(\min(open, close) - low) \ge 0.50 \times (high - low)$$
    - Close recovers back strictly inside Lower Band ($close > bb\_lower$).
    - Candle body is in upper half: $\min(open, close) \ge (low + 0.40 \times (high - low))$.
    - **Guards**:
      - $RSI \le 32.0$ (oversold exhaustion).
      - $ADX \le 25.0$.
      - $Bandwidth > 5.0$.
- **Stop Loss**: $high + \max(1.0, 0.0005 \times close)$ for PE; $low - \max(1.0, 0.0005 \times close)$ for CE.
- **Target 1**: 20-SMA Middle Band ($bb\_middle$).
- **Target 2**: Opposite $0.25\ \%B$ level.

---

### 2.3 Setup 7: Extreme 2.5σ Band Puncture & Inside Bar Breakdown
- **Timeframe**: 5m candles.
- **Direction & Triggers**:
  - **Bearish PE Entry**:
    - Candle $t-1$ (Mother Bar) punctures extreme upper band ($high_{t-1} \ge bb\_upper_{2.5}$).
    - Candle $t$ (Inside Bar) stays strictly within Mother Bar:
      $$high_t \le high_{t-1} \quad \text{and} \quad low_t \ge low_{t-1}$$
    - Current price breaks below Inside Bar low ($close \le low_t$ or tick crosses below $low_t$).
    - $Bandwidth > 5.0$.
  - **Bullish CE Entry**:
    - Candle $t-1$ punctures extreme lower band ($low_{t-1} \le bb\_lower_{2.5}$).
    - Candle $t$ stays strictly within Mother Bar:
      $$high_t \le high_{t-1} \quad \text{and} \quad low_t \ge low_{t-1}$$
    - Current price breaks above Inside Bar high ($close \ge high_t$ or tick crosses above $high_t$).
    - $Bandwidth > 5.0$.
- **Stop Loss**: High of Mother Bar ($high_{t-1}$) for PE; Low of Mother Bar ($low_{t-1}$) for CE.
- **Target 1**: 20-SMA Middle Band ($bb\_middle$).
- **Target 2**: Opposite $2.0\sigma$ Band ($bb\_lower$ for PE, $bb\_upper$ for CE).

---

### 2.4 Setup 8: Climax Swing RSI Divergence Fade (Early Sniper)
- **Timeframe**: 5m candles.
- **Direction & Triggers**:
  - **Bearish PE Entry**:
    - Swing Peak 1 (within last 15 candles): $high_1 \ge bb\_upper_1$.
    - Swing Peak 2 (recent 3 candles): Tests or exceeds Peak 1 ($high_2 \ge high_1 \times 0.998$).
    - Clear Bearish RSI Divergence: $RSI_2 < RSI_1 - 2.0$.
    - Current candle closes back inside Upper Band ($close < bb\_upper$).
  - **Bullish CE Entry**:
    - Swing Trough 1 (within last 15 candles): $low_1 \le bb\_lower_1$.
    - Swing Trough 2 (recent 3 candles): Tests or breaks below Trough 1 ($low_2 \le low_1 \times 1.002$).
    - Clear Bullish RSI Divergence: $RSI_2 > RSI_1 + 2.0$.
    - Current candle closes back inside Lower Band ($close > bb\_lower$).
- **Stop Loss**: Extreme price of Swing 2 ($high_2$ for PE, $low_2$ for CE).
- **Target 1**: 20-SMA Middle Band ($bb\_middle$).
- **Target 2**: Prior Swing 1 neckline level.

---

## 3. Strike Selection Mechanics (ATM / 1-Strike ITM)
In `backend/app/services/strike_selector.py`:
- Add parameter `strike_preference: Literal["DEFAULT", "ATM", "ITM_1"] = "DEFAULT"`.
- For Setups 6, 7, and 8, use `strike_preference="ITM_1"`:
  - If Option Type is **CE**: Select strike 1 tier below ATM (e.g. Spot 25,020 $\rightarrow$ ATM 25,000 $\rightarrow$ ITM_1 is `24,950 CE`).
  - If Option Type is **PE**: Select strike 1 tier above ATM (e.g. Spot 25,020 $\rightarrow$ ATM 25,050 $\rightarrow$ ITM_1 is `25,100 PE`).
  - Delta is $\approx 0.52 - 0.56$, providing sharp delta acceleration on snapback moves with low theta drag.
- Option target 1 and target 2 points are derived directly from underlying distance to 20-SMA scaled by Delta:
  $$\Delta P_{\text{opt}} = |Spot_{\text{entry}} - 20\text{-SMA}| \times 0.52$$

---

## 4. Frontend UI Extensions
In `frontend/src/components/PaperPortfolioView.tsx` and `frontend/src/types/index.ts`:
1. **Setup Filter Tabs**:
   Update filter pills:
   - `All Setups`
   - `Setup 1 (Squeeze)`
   - `Setup 2 (Walking Bands)`
   - `Setup 3 (W/M Reversal)`
   - `Setup 4 (ORB 9:30 AM)`
   - `Setup 5 (Option Chart)`
   - `Setup 6 (Pin Bar Snapback)`
   - `Setup 7 (2.5σ Inside Bar)`
   - `Setup 8 (Climax Divergence)`
2. **Setup Matching Function**:
   Update `matchSetup(tradeSetup: string, filter: string)` to recognize:
   - `SETUP_6_PINBAR_SNAPBACK` / `Setup 6` / `PIN_BAR`
   - `SETUP_7_INSIDE_BAR_SNAPBACK` / `Setup 7` / `INSIDE_BAR`
   - `SETUP_8_DIVERGENCE_SNAPBACK` / `Setup 8` / `DIVERGENCE`
3. **Dynamic Summary Strip**:
   Instantly recalculates filtered trades count, win rate %, gross P&L, net P&L, and slippage cost for any clicked setup.
4. **Signals Feed Badges**:
   Badge styling in `SignalsFeed.tsx` for Setups 6, 7, and 8 with distinct color accents (Amber/Purple for Pin Bar, Indigo for Inside Bar, Cyan for Climax Divergence).

---

## 5. Backward Compatibility & Non-Breaking Design
- Existing Setups 1–5 algorithms and test cases remain 100% untouched.
- Paper trading positions and SQLite database schema are fully compatible because `setup_type` is stored as text.
- Frontend defaults to `ALL` filter, displaying existing trade journals seamlessly.

---

## 6. Verification & Test Plan
1. **Indicator Tests (`backend/tests/test_indicators.py`)**:
   - Verify `bb_upper_25` and `bb_lower_25` columns computation.
2. **Snapback Strategy Unit Tests (`backend/tests/test_snapback_setups.py`)**:
   - Test Setup 6 PE pin bar trigger with high upper shadow.
   - Test Setup 6 CE pin bar trigger with high lower shadow.
   - Test Setup 6 suppression when $ADX > 25$.
   - Test Setup 7 PE & CE inside bar breakout.
   - Test Setup 8 PE & CE climax divergence triggers.
   - Test ATM/1-ITM strike selection for snapback setups.
3. **Full Backend Pytest Regression**:
   - All 189 existing tests pass cleanly without regression.
4. **Frontend Vitest Suite (`frontend/src/components/PaperPortfolioView.test.tsx`)**:
   - Test filtering by Setups 6, 7, and 8.
   - Test 0-trade safe win rate display (`0.0%`).
   - Clean production build (`npm run build`).
5. **GCP VM Deployment**:
   - Rsync to `34.14.178.224`, restart service, verify live state endpoint.
