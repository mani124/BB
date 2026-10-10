# Mean-Reversion 20-SMA Snapback Strategies (Setups 6, 7 & 8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three distinct, high-probability Mean-Reversion 20-SMA Snapback trading strategies (Setup 6: Rejection Pin Bar Exhaustion, Setup 7: Extreme 2.5σ Inside Bar Breakdown, Setup 8: Climax Swing RSI Divergence Fade) with ATM/1-ITM strike selection, paper trading execution, and frontend filter tabs.

**Architecture:** 
1. `indicators.py` computes extreme $2.5\sigma$ bands ($bb\_upper_{2.5}, bb\_lower_{2.5}$).
2. `strategy_engine.py` detects Setups 6, 7, and 8 on 5m candles with ADX non-trend filters ($ADX \le 25$) and RSI exhaustion boundaries.
3. `strike_selector.py` routes snapbacks to ATM or 1-Strike ITM contracts (Delta $\approx 0.52$) with dynamic 20-SMA targets.
4. `PaperPortfolioView.tsx` and `SignalsFeed.tsx` expose dedicated setup filter pills, summary metrics, and visual badges.

**Tech Stack:** Python 3.11+, FastAPI, Pandas, NumPy, React 18, TypeScript, TailwindCSS, Vitest, Pytest.

**Spec:** [`docs/superpowers/specs/2026-10-10-snapback-mean-reversion-setups-design.md`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/docs/superpowers/specs/2026-10-10-snapback-mean-reversion-setups-design.md)

## Global Constraints
- Target Location: Strictly inside `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD`.
- Zero-Token Persistence: Tokens and credentials remain in memory only.
- Strategy Integrity: Setups 1–5 logic, existing endpoints, and database schema must not be broken or altered.
- Safe Math: All ratios guarded against zero-division ($high - low == 0$, $bandwidth \le 0$).
- Intraday Cutoff: No fresh entries triggered after 15:15 IST.
- Production Deploy: Complete rsync to GCP VM (`34.14.178.224`), restart systemd service, verify HTTP 200, push to `origin/main`.

## Review Focus
1. **$2.5\sigma$ Mathematical Equivalence**: Assert $bb\_upper_{2.5}$ equals $bb\_middle + 2.5 \times \sigma$ and $\%B = 1.125$ at upper extreme.
2. **ADX Runaway Trend Invalidation**: Assert Setup 6 produces 0 signals when $ADX > 25.0$ even if candle is an ideal pin bar.
3. **Inside Bar Strict Containment**: Assert Setup 7 triggers only when bar $t$ high/low is strictly within bar $t-1$ range.
4. **Delta Responsiveness**: Assert snapbacks select ATM / 1-ITM strike with Delta $\approx 0.52$.
5. **Zero-Trade Safe Formatting**: Frontend setup filter displays `0.0% Win Rate` without `NaN%` when no trades match a setup.

---

### Task 1: Extreme 2.5σ Indicators Computation

**Files:**
- Modify: `backend/app/services/indicators.py`
- Test: `backend/tests/test_indicators_extreme_bands.py`

**Interfaces:**
- Consumes: OHLC DataFrame with `close`.
- Produces: `bb_upper_25` and `bb_lower_25` series added to indicator DataFrame and `INDICATOR_COLUMNS`.

- [ ] **Step 1: Write failing test for 2.5σ bands**

Create `backend/tests/test_indicators_extreme_bands.py`:
```python
import numpy as np
import pandas as pd
from app.services.indicators import calculate_indicators

def test_extreme_25_sigma_bands_calculation():
    # 20 bars of linear close prices
    closes = np.linspace(100, 120, 25)
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-10-10 09:15", periods=25, freq="5min"),
        "open": closes - 0.5,
        "high": closes + 1.0,
        "low": closes - 1.0,
        "close": closes,
        "volume": [1000] * 25
    })
    res = calculate_indicators(df)
    assert "bb_upper_25" in res.columns
    assert "bb_lower_25" in res.columns
    last = res.iloc[-1]
    expected_upper_25 = last["bb_middle"] + 2.5 * last["bb_std"]
    expected_lower_25 = last["bb_middle"] - 2.5 * last["bb_std"]
    assert np.isclose(last["bb_upper_25"], expected_upper_25)
    assert np.isclose(last["bb_lower_25"], expected_lower_25)
    assert last["bb_upper_25"] > last["bb_upper"]
    assert last["bb_lower_25"] < last["bb_lower"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_indicators_extreme_bands.py -v`
Expected: FAIL due to missing `bb_upper_25`.

- [ ] **Step 3: Implement 2.5σ bands in `indicators.py`**

In `backend/app/services/indicators.py`:
- Add `"bb_upper_25"`, `"bb_lower_25"` to `INDICATOR_COLUMNS`.
- Compute:
  ```python
  res["bb_upper_25"] = res["bb_middle"] + 2.5 * res["bb_std"]
  res["bb_lower_25"] = res["bb_middle"] - 2.5 * res["bb_std"]
  ```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_indicators_extreme_bands.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite & commit**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -q`
```bash
git add backend/app/services/indicators.py backend/tests/test_indicators_extreme_bands.py
git commit -m "feat(indicators): compute extreme 2.5 sigma Bollinger Bands"
```

---

### Task 2: Strategy Engine Snapback Setups (Setups 6, 7 & 8)

**Files:**
- Modify: `backend/app/services/strategy_engine.py`
- Test: `backend/tests/test_snapback_setups.py`

**Interfaces:**
- Consumes: Indicator DataFrame containing 20-SMA, 2.0σ & 2.5σ bands, RSI, ADX, VWAP.
- Produces: Signals for `SETUP_6_PINBAR_SNAPBACK`, `SETUP_7_INSIDE_BAR_SNAPBACK`, `SETUP_8_DIVERGENCE_SNAPBACK`.

- [ ] **Step 1: Write failing tests for Setups 6, 7, and 8**

Create `backend/tests/test_snapback_setups.py` testing:
1. Setup 6 Bearish PE Pin Bar: High > Upper Band, Upper Wick $\ge 50\%$, Close < Upper Band, RSI $\ge 68$, ADX $\le 25$.
2. Setup 6 Trend Invalidation: When ADX $= 32$, returns 0 signals.
3. Setup 6 Bullish CE Pin Bar: Low < Lower Band, Lower Wick $\ge 50\%$, Close > Lower Band, RSI $\le 32$, ADX $\le 25$.
4. Setup 7 Extreme 2.5σ Inside Bar: Bar $t-1$ high $> bb\_upper_{2.5}$, Bar $t$ inside bar, trigger below Inside Bar low.
5. Setup 8 Climax RSI Divergence: Peak 1 $> bb\_upper$, Peak 2 $\ge Peak 1$, RSI 2 < RSI 1, closes back inside.

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_snapback_setups.py -v`
Expected: FAIL due to missing SetupType enum values or logic.

- [ ] **Step 3: Implement Setups 6, 7, and 8 in `strategy_engine.py`**

In `backend/app/services/strategy_engine.py`:
- Add enum types:
  ```python
  SETUP_6_PINBAR_SNAPBACK = "Setup 6: Pin Bar Exhaustion Snapback"
  SETUP_7_INSIDE_BAR_SNAPBACK = "Setup 7: 2.5σ Puncture & Inside Bar"
  SETUP_8_DIVERGENCE_SNAPBACK = "Setup 8: Climax Swing Divergence Fade"
  ```
- Implement detection routines with mathematical safeguards ($BW > 5.0$, non-zero ranges, target at $bb\_middle$).

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_snapback_setups.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite & commit**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -q`
```bash
git add backend/app/services/strategy_engine.py backend/tests/test_snapback_setups.py
git commit -m "feat(strategy): implement Setups 6, 7 and 8 mean-reversion snapback detectors"
```

---

### Task 3: Strike Selector ATM / 1-ITM Routing for Snapbacks

**Files:**
- Modify: `backend/app/services/strike_selector.py`
- Test: `backend/tests/test_snapback_strike_selector.py`

**Interfaces:**
- Consumes: Underlying price, signal direction, option type, target 20-SMA.
- Produces: `OptionStrikeRecommendation` with ATM or 1-Strike ITM contract and delta-scaled targets.

- [ ] **Step 1: Write failing test for snapback strike selection**

Create `backend/tests/test_snapback_strike_selector.py`:
```python
from app.services.strike_selector import recommend_strike

def test_snapback_strike_selection_itm_1_pe():
    # Spot 25020. For PE, ATM is 25000/25050. 1-ITM is 25100 PE.
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25020.0,
        option_type="PE",
        stop_loss=25055.0,
        target_1=24950.0, # 20-SMA midline
        strike_preference="ITM_1"
    )
    assert rec.recommended_strike >= 25050
    assert "PE" in rec.strike_symbol
    assert rec.option_target_1_pts > 0

def test_snapback_strike_selection_itm_1_ce():
    # Spot 24980. For CE, ATM is 25000. 1-ITM is 24950 CE.
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=24980.0,
        option_type="CE",
        stop_loss=24945.0,
        target_1=25050.0,
        strike_preference="ITM_1"
    )
    assert rec.recommended_strike <= 24950
    assert "CE" in rec.strike_symbol
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_snapback_strike_selector.py -v`
Expected: FAIL due to missing `strike_preference` parameter.

- [ ] **Step 3: Implement `strike_preference` in `strike_selector.py`**

In `backend/app/services/strike_selector.py`:
- Add `strike_preference: str = "DEFAULT"` to `recommend_strike` and `resolve_live_strike_from_chain`.
- If `strike_preference == "ITM_1"`:
  - For `CE`: select strike 1 interval below ATM (`atm_strike - strike_step`).
  - For `PE`: select strike 1 interval above ATM (`atm_strike + strike_step`).
  - Set estimated delta to `0.54`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_snapback_strike_selector.py -v`
Expected: PASS.

- [ ] **Step 5: Run full test suite & commit**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -q`
```bash
git add backend/app/services/strike_selector.py backend/tests/test_snapback_strike_selector.py
git commit -m "feat(strikes): support ATM and 1-ITM strike selection for snapback setups"
```

---

### Task 4: Scanner Worker & Paper Trader Integration

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Test: `backend/tests/test_scanner_snapback_wiring.py`

**Interfaces:**
- Consumes: Scanned signals from `strategy_engine.py` (Setups 1–8).
- Produces: Real-time scan cycle execution and paper trade fills with slippage & charges tracking for Setups 6, 7, and 8.

- [ ] **Step 1: Write failing integration test**

Create `backend/tests/test_scanner_snapback_wiring.py`:
- Verify scanner loop dispatches Setups 6, 7, and 8 signals into `paper_trader`.
- Verify `paper_trader.get_portfolio().closed_trades` tracks positions with `setup_type` Setups 6–8.

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_scanner_snapback_wiring.py -v`
Expected: FAIL.

- [ ] **Step 3: Wire Setups 6, 7, and 8 in `scanner_worker.py`**

Ensure `resolve_live_strike_from_chain` passes `strike_preference="ITM_1"` when signal setup type is Setup 6, 7, or 8.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_scanner_snapback_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Run full backend test suite & commit**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -q`
```bash
git add backend/app/services/scanner_worker.py backend/tests/test_scanner_snapback_wiring.py
git commit -m "feat(scanner): wire snapback setups with ITM option chain resolution into scan loop"
```

---

### Task 5: Frontend Setup Filter Tabs, Badges & Dynamic Summary Strip

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/PaperPortfolioView.tsx`
- Modify: `frontend/src/components/SignalsFeed.tsx`
- Test: `frontend/src/components/PaperPortfolioView.test.tsx`

**Interfaces:**
- Consumes: `closed_trades` with `setup_type` (`SETUP_6_PINBAR_SNAPBACK`, `SETUP_7_INSIDE_BAR_SNAPBACK`, `SETUP_8_DIVERGENCE_SNAPBACK`).
- Produces: Setup filter tabs for Setups 6, 7, and 8, dynamic performance recalculation, and signal feed badges.

- [ ] **Step 1: Write failing frontend tests for Setups 6, 7, and 8 filters**

In `frontend/src/components/PaperPortfolioView.test.tsx`:
- Add test case with mock trades for Setups 6, 7, and 8.
- Verify clicking `Setup 6 (Pin Bar)` filters to only Setup 6 trades.
- Verify clicking `Setup 7` filters to Setup 7 trades.
- Verify clicking `Setup 8` filters to Setup 8 trades.

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/components/PaperPortfolioView.test.tsx` (in `frontend/`)
Expected: FAIL due to missing filter pills.

- [ ] **Step 3: Update `PaperPortfolioView.tsx`, `SignalsFeed.tsx`, and `types/index.ts`**

- In `frontend/src/types/index.ts`: Update `SetupType` union to include Setups 6, 7, and 8.
- In `frontend/src/components/PaperPortfolioView.tsx`:
  - Add Setup 6, 7, and 8 filter pills.
  - Update `matchSetup` helper to recognize `Setup 6` / `PINBAR`, `Setup 7` / `INSIDE_BAR`, `Setup 8` / `DIVERGENCE`.
- In `frontend/src/components/SignalsFeed.tsx`: Add badge rendering and color styles for Setups 6, 7, and 8.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run src/components/PaperPortfolioView.test.tsx` (in `frontend/`)
Expected: PASS.

- [ ] **Step 5: Run full frontend test suite & typecheck**

Run: `npm test -- --run` and `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/PaperPortfolioView.tsx frontend/src/components/SignalsFeed.tsx frontend/src/components/PaperPortfolioView.test.tsx
git commit -m "feat(ui): add Setups 6, 7 and 8 filter tabs, dynamic summary strip, and signal badges"
```

---

### Task 6: Full Verification, Production Build & GCP VM Deployment

**Files:**
- Repository-wide verification.
- Remote GCP VM: `mani_vutla7@34.14.178.224`

- [ ] **Step 1: Run complete backend pytest suite**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`
Expected: PASS with 195+ passed, 0 failures.

- [ ] **Step 2: Run frontend vitest suite and build**

Run in `frontend/`:
```bash
npm test -- --run
npm run build
```
Expected: All Vitest suites PASS, `dist/` builds with 0 errors.

- [ ] **Step 3: Deploy to Remote GCP VM**

```bash
rsync -avz -e "ssh -i /Users/manigopal/.ssh/google_compute_engine -o StrictHostKeyChecking=no" \
  --exclude 'node_modules' --exclude '.git' --exclude 'venv' --exclude '__pycache__' --exclude '.pytest_cache' \
  /Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/ mani_vutla7@34.14.178.224:/home/mani_vutla7/BB_OPTIONS_DASHBOARD/

ssh -i /Users/manigopal/.ssh/google_compute_engine -o StrictHostKeyChecking=no mani_vutla7@34.14.178.224 \
  "sudo systemctl restart bb-options && sudo systemctl status bb-options --no-pager"
```
Expected: `systemctl status` shows `active (running)`.

- [ ] **Step 4: Verify production endpoints**

```bash
curl -k https://options.34-14-178-224.sslip.io/api/health
curl -k https://options.34-14-178-224.sslip.io/api/signals/state
```
Expected: HTTP 200 OK with `status: "healthy"`.

- [ ] **Step 5: Push all changes to git**

```bash
git push origin main
```
Expected: Remote `mani124/BB.git` updated to latest commit.
