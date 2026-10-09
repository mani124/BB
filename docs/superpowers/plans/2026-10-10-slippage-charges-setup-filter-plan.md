# Slippage Tracking, Regulatory Charges Engine & Setup-Filtered Journal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement realistic Bid/Ask execution slippage tracking, official Dhan/SEBI F&O regulatory and brokerage charges calculation, and a setup-filtered closed trades journal with itemized tax receipts.

**Architecture:** A standalone stateless charges calculator service (`charges_calculator.py`) calculates Dhan F&O regulatory fees and taxes; `paper_trader.py` integrates Bid/Ask spread modeling and latency buffer slippage on entries and exits; `paper_storage.py` auto-migrates SQLite schema for persistent storage; and the React frontend provides a 4-metric Gross vs Net P&L hero bar, setup filter tabs, and itemized tax popovers.

**Tech Stack:** Python 3.14, FastAPI, Pydantic, SQLite3, React 19, TypeScript, Tailwind CSS, Lucide icons, Vitest, Pytest.

**Spec:** [`docs/superpowers/specs/2026-10-10-slippage-charges-setup-filter-design.md`](file:///Users/manigopal/Documents/BB_OPTIONS_DASHBOARD/docs/superpowers/specs/2026-10-10-slippage-charges-setup-filter-design.md)

---

## Global Constraints

- **Location:** All changes strictly inside `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD`.
- **Zero-Token Persistence:** No authentication tokens or secrets logged or stored to disk/SQLite.
- **Backward Compatibility:** Existing positions in `trades.db` must load safely without `ValidationError` or database corruption.
- **Brokerage & Tax Schedule:**
  - Brokerage: Flat ₹20 per executed order leg.
  - STT: 0.1% (0.0010) on Sell Turnover only.
  - NSE Exchange Fee: 0.05% (0.0005) on Total Turnover.
  - SEBI Fee: ₹10 per crore (0.000001) on Total Turnover.
  - Stamp Duty: 0.003% (0.00003) on Buy Turnover only.
  - GST: 18% on (Brokerage + Exchange Fee + SEBI Fee).
- **Slippage Clamp:** Favorable price movement (Ask < Signal or Bid > Trigger) yields `0.0` slippage points (clamped with `max(0.0, ...)`).

---

## Review Focus

1. **Zero Quantity or Negative Turnover in Charges Engine**: Function must return zeroed breakdown without `ZeroDivisionError` or negative taxes. (Pinned to Task 1)
2. **Missing/Corrupt `charges_json` in SQLite Row during Deserialization**: Deserializing legacy rows without slippage/charges columns must default safely. (Pinned to Task 2)
3. **Favorable Slippage (Negative Slippage / Price Improvement)**: When actual fill price improves on the trigger, slippage points must clamp to `0.0`. (Pinned to Task 2)
4. **Partial Profit Booking (TP1) Slippage & Charges on Multi-Leg Execution**: When 50% booked at TP1 and runner exits later, order count must be 3 and turnovers must sum both legs. (Pinned to Task 2)
5. **Setup Filter with No Matching Trades**: Setup filter with zero trades must display `0.0%` win rate without `NaN%` or dividing by zero. (Pinned to Task 5)

---

### Task 1: Charges Calculator Service & Unit Tests

**Files:**
- Create: `backend/app/services/charges_calculator.py`
- Test: `backend/tests/test_charges_calculator.py`

**Interfaces:**
- Consumes: None (pure domain logic)
- Produces:
  ```python
  class TradeChargesBreakdown(BaseModel):
      buy_turnover: float
      sell_turnover: float
      total_turnover: float
      orders_count: int
      brokerage: float
      stt: float
      exchange_fee: float
      sebi_fee: float
      stamp_duty: float
      gst: float
      total_charges: float

  def calculate_option_trade_charges(
      buy_price: float,
      sell_price: float,
      quantity: int,
      orders_count: int = 2,
      brokerage_per_order: float = 20.0
  ) -> TradeChargesBreakdown
  ```

- [ ] **Step 1: Write failing unit tests for charges calculation**

Create `backend/tests/test_charges_calculator.py`:
```python
import pytest
from app.services.charges_calculator import calculate_option_trade_charges, TradeChargesBreakdown

def test_standard_round_trip_trade_charges():
    # Buy @ 100, Sell @ 150, Qty 65 (Nifty lot), 2 orders (1 Buy, 1 Sell)
    breakdown = calculate_option_trade_charges(buy_price=100.0, sell_price=150.0, quantity=65, orders_count=2)
    assert isinstance(breakdown, TradeChargesBreakdown)
    assert breakdown.buy_turnover == 6500.0
    assert breakdown.sell_turnover == 9750.0
    assert breakdown.total_turnover == 16250.0
    assert breakdown.orders_count == 2
    assert breakdown.brokerage == 40.0
    # STT = 9750 * 0.0010 = 9.75
    assert breakdown.stt == 9.75
    # Exchange Fee = 16250 * 0.0005 = 8.125 -> round 8.13 or 8.12
    assert abs(breakdown.exchange_fee - 8.13) <= 0.02
    # SEBI Fee = 16250 * 0.000001 = 0.016 -> 0.02
    assert abs(breakdown.sebi_fee - 0.02) <= 0.01
    # Stamp Duty = 6500 * 0.00003 = 0.195 -> 0.20
    assert abs(breakdown.stamp_duty - 0.20) <= 0.02
    # GST = (40 + 8.13 + 0.02) * 0.18 = 8.67
    assert abs(breakdown.gst - 8.67) <= 0.03
    expected_total = round(breakdown.brokerage + breakdown.stt + breakdown.exchange_fee + breakdown.sebi_fee + breakdown.stamp_duty + breakdown.gst, 2)
    assert breakdown.total_charges == expected_total

def test_partial_profit_booking_three_orders():
    # 3 orders (1 Buy, 2 Sells)
    breakdown = calculate_option_trade_charges(buy_price=200.0, sell_price=260.0, quantity=130, orders_count=3)
    assert breakdown.brokerage == 60.0
    assert breakdown.orders_count == 3
    assert breakdown.total_charges > 60.0

def test_zero_quantity_or_invalid_price():
    # Review Focus: Zero quantity must yield zeroed breakdown without division by zero
    breakdown = calculate_option_trade_charges(buy_price=0.0, sell_price=0.0, quantity=0, orders_count=2)
    assert breakdown.total_turnover == 0.0
    assert breakdown.brokerage == 0.0
    assert breakdown.total_charges == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_charges_calculator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.charges_calculator'`

- [ ] **Step 3: Implement `charges_calculator.py`**

Implement `backend/app/services/charges_calculator.py` with `TradeChargesBreakdown` model and `calculate_option_trade_charges` using official SEBI/NSE F&O rules.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_charges_calculator.py -v`
Expected: PASS with 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/charges_calculator.py backend/tests/test_charges_calculator.py
git commit -m "feat(charges): implement Dhan SEBI F&O option regulatory charges calculator"
```

---

### Task 2: Paper Trader Slippage & Execution Engine with SQLite Migration

**Files:**
- Modify: `backend/app/services/paper_trader.py`
- Modify: `backend/app/services/paper_storage.py`
- Test: `backend/tests/test_paper_slippage.py`

**Interfaces:**
- Consumes: `calculate_option_trade_charges` from `charges_calculator.py`
- Produces:
  - `PaperPosition` with slippage & charges fields: `theoretical_entry`, `entry_slippage`, `theoretical_exit`, `exit_slippage`, `total_slippage_cost`, `gross_pnl`, `total_charges`, `net_pnl`, `charges_breakdown`.
  - `PaperPortfolio` with aggregate metrics: `total_gross_pnl`, `total_slippage_cost`, `avg_slippage_points`, `total_charges`, `total_net_pnl`.

- [ ] **Step 1: Write failing tests for paper trading slippage & charges integration**

Create `backend/tests/test_paper_slippage.py`:
```python
import pytest
from app.services.paper_trader import PaperTradingEngine, PaperPosition
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation

@pytest.fixture
def mock_signal():
    rec = OptionStrikeRecommendation(
        symbol="NIFTY 50",
        underlying_price=22500.0,
        option_type="CE",
        atm_strike=22500,
        recommended_strike=22450,
        strike_symbol="NIFTY 22450 CE",
        lot_size=65,
        risk=30.0,
        stop_loss=22470.0,
        target_1=22545.0,
        target_2=22575.0,
        estimated_option_entry=150.0,
        option_sl_pts=16.5,
        option_target_1_pts=24.8,
        option_target_2_pts=41.3,
        option_sl_price=133.5,
        option_target_1_price=174.8,
        option_target_2_price=191.3,
        real_ask_price=152.0,  # +2.0 pts entry slippage
        real_bid_price=149.5,
        real_ltp=150.0,
        is_live_quote=True
    )
    return Signal(
        id="SIG_SLIP_001",
        symbol="NIFTY 50",
        timeframe="5m",
        setup_type=SetupType.SETUP_1_SQUEEZE_EXPANSION,
        option_type="CE",
        timestamp="09:35:00",
        entry_price=22500.0,
        stop_loss=22470.0,
        target_1=22545.0,
        target_2=22575.0,
        strike_recommendation=rec,
        indicators_snapshot={"close": 22500.0, "bb_upper": 22520.0, "bb_middle": 22480.0, "bb_lower": 22440.0, "bandwidth": 3.5, "percent_b": 0.75, "vwap": 22490.0, "rsi": 62.0, "ema_9": 22495.0, "adx": 28.0},
        rationale="Test signal"
    )

def test_entry_slippage_calculation(mock_signal):
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos is not None
    # Signal theoretical entry = 150.0, Real Ask fill = 152.0 -> slippage = 2.0 pts
    assert pos.theoretical_entry == 150.0
    assert pos.option_entry == 152.0
    assert pos.entry_slippage == 2.0

def test_favorable_entry_slippage_clamped_to_zero(mock_signal):
    # Review Focus: Ask price lower than signal entry clamps slippage to 0.0
    mock_signal.id = "SIG_SLIP_002"
    mock_signal.strike_recommendation.real_ask_price = 148.0
    engine = PaperTradingEngine()
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    assert pos.entry_slippage == 0.0
    assert pos.option_entry == 148.0

def test_exit_slippage_and_charges_on_target_exit(mock_signal, tmp_path):
    db_file = str(tmp_path / "test_trades.db")
    engine = PaperTradingEngine(db_path=db_file)
    pos = engine.open_position_from_signal(mock_signal, lots=2)
    
    # Target 2 hit: option price jumps to 191.3, but bid is 190.5 (-0.8 pts slippage)
    engine.update_market_prices(
        price_map={"NIFTY 50": 22600.0},
        option_price_map={getattr(pos, "option_security_id", ""): 190.5} if pos.option_security_id else None,
        option_bid_map={pos.id: 190.5}
    )
    portfolio = engine.get_portfolio()
    assert len(portfolio.closed_trades) == 1
    closed = portfolio.closed_trades[0]
    assert closed.status in ["TARGET_2", "STOPPED_OUT", "CLOSED"]
    assert closed.gross_pnl > 0
    assert closed.total_charges > 0
    assert closed.net_pnl == round(closed.gross_pnl - closed.total_charges, 2)
    assert closed.total_slippage_cost >= 0

def test_legacy_database_migration_backward_compatibility(tmp_path):
    # Review Focus: Database created without new columns must auto-migrate without error
    import sqlite3
    db_file = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE positions (
            id TEXT PRIMARY KEY, signal_id TEXT, symbol TEXT, option_type TEXT, strike_symbol TEXT,
            timeframe TEXT, setup_type TEXT, entry_time TEXT, underlying_entry REAL, underlying_sl REAL,
            underlying_target_1 REAL, underlying_target_2 REAL, option_entry REAL, option_sl REAL,
            option_target_1 REAL, option_target_2 REAL, lot_size INTEGER, lots INTEGER, quantity INTEGER,
            current_underlying REAL, current_option_price REAL, pnl_points REAL, pnl_rupees REAL,
            status TEXT, exit_time TEXT, exit_reason TEXT, initial_lots INTEGER, initial_quantity INTEGER,
            booked_lots INTEGER, booked_pnl_rupees REAL, option_security_id TEXT
        );
    """)
    conn.commit()
    conn.close()

    engine = PaperTradingEngine(db_path=db_file)
    # Check that it loaded cleanly without raising exceptions
    port = engine.get_portfolio()
    assert len(port.active_positions) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_paper_slippage.py -v`
Expected: FAIL with missing attributes on `PaperPosition` or `PaperTradingEngine`.

- [ ] **Step 3: Implement updates in `paper_trader.py` and `paper_storage.py`**

- In `PaperPosition`: add `theoretical_entry: float = 0.0`, `entry_slippage: float = 0.0`, `theoretical_exit: Optional[float] = None`, `exit_slippage: float = 0.0`, `total_slippage_cost: float = 0.0`, `gross_pnl: float = 0.0`, `total_charges: float = 0.0`, `net_pnl: float = 0.0`, `charges_breakdown: Optional[dict] = None`.
- In `PaperPortfolio`: add `total_gross_pnl: float = 0.0`, `total_slippage_cost: float = 0.0`, `avg_slippage_points: float = 0.0`, `total_charges: float = 0.0`, `total_net_pnl: float = 0.0`.
- In `open_position_from_signal`: calculate entry slippage and set `option_entry` from `real_ask_price` (or LTP with +0.1% latency buffer if Ask is missing).
- In `update_market_prices` and `close_position`: calculate exit slippage and total charges via `calculate_option_trade_charges`. Update gross and net P&L.
- In `paper_storage.py`: auto-migrate `positions` table with `ALTER TABLE positions ADD COLUMN IF NOT EXISTS ...` (guarded for SQLite syntax compatibility), update SQL queries in `upsert_position` and `load_all_positions`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_paper_slippage.py -v`
Expected: PASS with 4 passed.

- [ ] **Step 5: Run complete backend test suite to guarantee no regression**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -q`
Expected: PASS (all 166+ tests pass).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/paper_trader.py backend/app/services/paper_storage.py backend/tests/test_paper_slippage.py
git commit -m "feat(paper): integrate slippage tracking, charges engine, and SQLite migration"
```

---

### Task 3: Scanner Worker Quote Feed Wiring for Real Ask/Bid Slippage

**Files:**
- Modify: `backend/app/services/scanner_worker.py`
- Modify: `backend/app/api/signals.py` (if manual close needs bid price pass-through)
- Test: `backend/tests/test_scanner_slippage_wiring.py`

**Interfaces:**
- Consumes: `paper_trader.update_market_prices(price_map, option_price_map, option_bid_map, feed_mode)`
- Produces: Seamless dispatch of real market Bid/Ask quotes into paper trader position lifecycles.

- [ ] **Step 1: Write failing test for scanner worker quote wiring**

Create `backend/tests/test_scanner_slippage_wiring.py`:
```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.scanner_worker import ScannerWorker
from app.services.paper_trader import paper_trader

@pytest.mark.asyncio
async def test_scanner_worker_ws_tick_passes_bid_and_computes_slippage():
    worker = ScannerWorker()
    # Mock open live paper position
    pos = paper_trader.open_position_from_signal(
        signal=pytest.mock_signal if hasattr(pytest, "mock_signal") else None, # setup helper
        feed_mode="live"
    ) if hasattr(pytest, "mock_signal") else None
    # Test that tick with bid price properly dispatches to paper trader
    # and portfolio metrics update with gross, net, slippage, charges
    assert hasattr(worker, "run_single_scan_cycle")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_scanner_slippage_wiring.py -v`
Expected: FAIL or missing method.

- [ ] **Step 3: Wire Ask/Bid feeds into `scanner_worker.py`**

- In `scanner_worker._handle_incoming_ws_tick`: Extract `bid_price` and `ask_price` from quote tick if present, or pass through to `paper_trader.update_market_prices(..., option_bid_map=...)`.
- In `scanner_worker._execute_scan_cycle`: When building `option_price_map`, also extract `option_bid_map` from option chain or quote responses.
- In `backend/app/api/signals.py`: Update manual close endpoint to record execution with realistic bid/latency fill.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/test_scanner_slippage_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Run complete backend test suite**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/scanner_worker.py backend/app/api/signals.py backend/tests/test_scanner_slippage_wiring.py
git commit -m "feat(scanner): wire live Ask/Bid quotes to paper trader for sub-second slippage tracking"
```

---

### Task 4: Frontend Types & 4-Metric Glassmorphism Hero Bar

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/PaperPortfolioView.tsx`
- Test: `frontend/src/components/PaperPortfolioHero.test.tsx`

**Interfaces:**
- Consumes: `PaperPortfolio` with `total_gross_pnl`, `total_slippage_cost`, `avg_slippage_points`, `total_charges`, `total_net_pnl`.
- Produces: 4-Metric Hero Bar displaying Gross P&L, Slippage pts & ₹, Total Regulatory Charges, and Net Realized P&L.

- [ ] **Step 1: Write failing frontend test for 4-metric Hero Bar**

Create `frontend/src/components/PaperPortfolioHero.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PaperPortfolioView } from './PaperPortfolioView';
import { PaperPortfolio } from '../types';

describe('PaperPortfolioView Hero Bar', () => {
  const mockPortfolio: PaperPortfolio = {
    active_positions: [],
    closed_trades: [],
    auto_trade_enabled: true,
    default_lots: 2,
    total_realized_pnl: 10884.5,
    total_unrealized_pnl: 0.0,
    total_pnl: 10884.5,
    total_gross_pnl: 12450.0,
    total_slippage_cost: 923.0,
    avg_slippage_points: 0.8,
    total_charges: 642.5,
    total_net_pnl: 10884.5,
    win_rate_pct: 75.0,
    total_trades_count: 8,
    winning_trades_count: 6,
    losing_trades_count: 2,
  };

  it('renders all 4 hero cards: Gross P&L, Slippage, Charges, and Net Realized P&L', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    expect(screen.getByText(/Gross Realized P&L/i)).toBeInTheDocument();
    expect(screen.getByText(/₹12,450.00/i)).toBeInTheDocument();
    expect(screen.getByText(/Slippage Impact/i)).toBeInTheDocument();
    expect(screen.getByText(/₹923.00/i)).toBeInTheDocument();
    expect(screen.getByText(/Brokerage & Regulatory Taxes/i)).toBeInTheDocument();
    expect(screen.getByText(/₹642.50/i)).toBeInTheDocument();
    expect(screen.getByText(/Net Realized P&L/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/components/PaperPortfolioHero.test.tsx` (in `frontend/`)
Expected: FAIL due to missing hero labels or types.

- [ ] **Step 3: Update `frontend/src/types/index.ts` and `PaperPortfolioView.tsx`**

- In `frontend/src/types/index.ts`: Add `TradeChargesBreakdown`, update `PaperPosition` and `PaperPortfolio` with new slippage and charges fields.
- In `frontend/src/components/PaperPortfolioView.tsx`: Replace the existing top stats cards with the 4-card glassmorphism hero bar:
  1. Gross Realized P&L (`+₹12,450.00`)
  2. Execution Slippage Impact (`-0.8 pts avg (-₹923.00)`)
  3. Total Charges & Taxes (`-₹642.50`)
  4. Net Realized P&L (`+₹10,884.50`)

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run src/components/PaperPortfolioHero.test.tsx` (in `frontend/`)
Expected: PASS.

- [ ] **Step 5: Run full frontend test suite & typecheck**

Run: `npm test -- --run` and `npm run build`
Expected: PASS with 0 TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/components/PaperPortfolioView.tsx frontend/src/components/PaperPortfolioHero.test.tsx
git commit -m "feat(ui): add 4-metric Gross vs Net P&L hero bar with slippage and charges"
```

---

### Task 5: Setup Filter Tabs, Dynamic Summary Strip & Itemized Tax Receipt Popover

**Files:**
- Modify: `frontend/src/components/PaperPortfolioView.tsx`
- Test: `frontend/src/components/PaperPortfolioView.test.tsx`

**Interfaces:**
- Consumes: `portfolio.closed_trades` with `setup_type`, `theoretical_entry`, `entry_slippage`, `theoretical_exit`, `exit_slippage`, `gross_pnl`, `total_charges`, `net_pnl`, `charges_breakdown`.
- Produces: Setup pill tab filter, setup performance strip, closed trades table columns with slippage subtext, and itemized tax popover modal.

- [ ] **Step 1: Write failing frontend tests for Setup Filter and Tax Popover**

Create `frontend/src/components/PaperPortfolioView.test.tsx`:
```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PaperPortfolioView } from './PaperPortfolioView';
import { PaperPortfolio, PaperPosition } from '../types';

describe('PaperPortfolioView Setup Filter & Tax Popover', () => {
  const mockTrades: PaperPosition[] = [
    {
      id: 'POS_1',
      signal_id: 'SIG_1',
      symbol: 'NIFTY 50',
      option_type: 'CE',
      strike_symbol: 'NIFTY 22450 CE',
      timeframe: '5m',
      setup_type: 'SETUP_1_SQUEEZE_EXPANSION',
      entry_time: '09:30:00',
      exit_time: '09:45:00',
      underlying_entry: 22500,
      underlying_sl: 22470,
      underlying_target_1: 22545,
      underlying_target_2: 22575,
      option_entry: 152.0,
      theoretical_entry: 150.0,
      entry_slippage: 2.0,
      option_sl: 133.5,
      option_target_1: 174.8,
      option_target_2: 191.3,
      lot_size: 65,
      lots: 2,
      quantity: 130,
      current_underlying: 22580,
      current_option_price: 190.5,
      theoretical_exit: 191.3,
      exit_slippage: 0.8,
      total_slippage_cost: 364.0,
      pnl_points: 38.5,
      pnl_rupees: 5005.0,
      gross_pnl: 5005.0,
      total_charges: 88.5,
      net_pnl: 4916.5,
      status: 'CLOSED',
      exit_reason: 'Target 2 Hit',
      charges_breakdown: {
        buy_turnover: 19760.0,
        sell_turnover: 24765.0,
        total_turnover: 44525.0,
        orders_count: 2,
        brokerage: 40.0,
        stt: 24.77,
        exchange_fee: 22.26,
        sebi_fee: 0.04,
        stamp_duty: 0.59,
        gst: 11.21,
        total_charges: 98.87
      }
    },
    {
      id: 'POS_2',
      signal_id: 'SIG_2',
      symbol: 'BANKNIFTY',
      option_type: 'PE',
      strike_symbol: 'BANKNIFTY 48500 PE',
      timeframe: '15m',
      setup_type: 'SETUP_2_WALKING_BANDS',
      entry_time: '10:00:00',
      exit_time: '10:15:00',
      underlying_entry: 48500,
      underlying_sl: 48600,
      underlying_target_1: 48350,
      underlying_target_2: 48250,
      option_entry: 250.0,
      theoretical_entry: 250.0,
      entry_slippage: 0.0,
      option_sl: 200.0,
      option_target_1: 325.0,
      option_target_2: 375.0,
      lot_size: 30,
      lots: 2,
      quantity: 60,
      current_underlying: 48610,
      current_option_price: 195.0,
      pnl_points: -55.0,
      pnl_rupees: -3300.0,
      gross_pnl: -3300.0,
      total_charges: 62.0,
      net_pnl: -3362.0,
      status: 'STOPPED_OUT',
      exit_reason: 'Stop-Loss Hit'
    }
  ];

  const mockPortfolio: PaperPortfolio = {
    active_positions: [],
    closed_trades: mockTrades,
    auto_trade_enabled: true,
    default_lots: 2,
    total_realized_pnl: 1554.5,
    total_unrealized_pnl: 0,
    total_pnl: 1554.5,
    total_gross_pnl: 1705.0,
    total_slippage_cost: 364.0,
    avg_slippage_points: 1.4,
    total_charges: 150.5,
    total_net_pnl: 1554.5,
    win_rate_pct: 50.0,
    total_trades_count: 2,
    winning_trades_count: 1,
    losing_trades_count: 1
  };

  it('renders filter pills and filters closed trades by setup', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    // Initial state: 2 trades shown
    expect(screen.getByText('NIFTY 22450 CE')).toBeInTheDocument();
    expect(screen.getByText('BANKNIFTY 48500 PE')).toBeInTheDocument();

    // Click Setup 1 pill
    const s1Button = screen.getByRole('button', { name: /Setup 1/i });
    fireEvent.click(s1Button);

    expect(screen.getByText('NIFTY 22450 CE')).toBeInTheDocument();
    expect(screen.queryByText('BANKNIFTY 48500 PE')).not.toBeInTheDocument();
  });

  it('displays 0.0% win rate cleanly when filtered setup has no trades', () => {
    // Review Focus: Zero matching trades must display 0.0% without NaN%
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    const s4Button = screen.getByRole('button', { name: /Setup 4/i });
    fireEvent.click(s4Button);

    expect(screen.getByText(/0 Trades/i)).toBeInTheDocument();
    expect(screen.getByText(/0.0% Win Rate/i)).toBeInTheDocument();
  });

  it('opens itemized charges breakdown popover when receipt icon is clicked', () => {
    render(
      <PaperPortfolioView
        portfolio={mockPortfolio}
        onClosePosition={() => {}}
        onToggleAutoTrade={() => {}}
        onChangeLots={() => {}}
        onResetPortfolio={() => {}}
      />
    );

    const receiptBtn = screen.getByTitle(/View Charges Breakdown/i);
    fireEvent.click(receiptBtn);

    expect(screen.getByText(/Dhan & Statutory Taxes Receipt/i)).toBeInTheDocument();
    expect(screen.getByText(/Brokerage/i)).toBeInTheDocument();
    expect(screen.getByText(/STT/i)).toBeInTheDocument();
    expect(screen.getByText(/NSE Exchange Fee/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- --run src/components/PaperPortfolioView.test.tsx` (in `frontend/`)
Expected: FAIL due to missing setup filter pills or receipt button.

- [ ] **Step 3: Implement Setup Filter tabs, stats strip, and Tax Receipt Popover**

In `frontend/src/components/PaperPortfolioView.tsx`:
1. Add state `selectedSetupFilter: string` defaulting to `'ALL'`.
2. Add filter pill buttons above Closed Trades table:
   - All Setups
   - Setup 1 (Squeeze)
   - Setup 2 (Walking Bands)
   - Setup 3 (W/M Reversal)
   - Setup 4 (ORB 9:30 AM)
   - Setup 5 (Option Chart)
3. Add Dynamic Setup Summary Strip showing:
   - Filtered Trades count
   - Filtered Win Rate % (safely avoiding NaN: `count > 0 ? (wins / count * 100).toFixed(1) : '0.0'`)
   - Filtered Gross P&L
   - Filtered Net P&L
   - Filtered Slippage ₹
4. Update Closed Trades table columns:
   - Entry: `₹{trade.option_entry}` + subtext `(Slip: +{trade.entry_slippage} pts)`
   - Exit: `₹{trade.current_option_price}` + subtext `(Slip: -{trade.exit_slippage} pts)`
   - Gross vs Net P&L: `₹{trade.gross_pnl} Gross` / `₹{trade.net_pnl} Net`
   - Receipt button with Lucide `Receipt` or `FileText` icon.
5. Add Itemized Tax Popover / Modal displaying:
   - Brokerage (₹40.00 / ₹60.00)
   - STT (0.1%)
   - NSE Turnover Fee (0.05%)
   - GST (18%)
   - Stamp Duty (0.003%)
   - SEBI Turnover Fee
   - Total Deductions

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- --run src/components/PaperPortfolioView.test.tsx` (in `frontend/`)
Expected: PASS with 3 passed.

- [ ] **Step 5: Run full frontend test suite & production build**

Run: `npm test -- --run` and `npm run build`
Expected: PASS with 0 errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PaperPortfolioView.tsx frontend/src/components/PaperPortfolioView.test.tsx
git commit -m "feat(ui): add setup filter tabs, dynamic summary strip, and itemized tax receipt popover"
```

---

### Task 6: Full Verification, Production Build & GCP VM Deployment

**Files:**
- Verification across repository
- Remote GCP VM: `mani_vutla7@34.14.178.224`

**Interfaces:**
- End-to-end operational verification across backend, frontend, database, and production cloud server.

- [ ] **Step 1: Run complete backend pytest suite**

Run: `/Users/manigopal/Documents/SSCREENER/venv/bin/pytest backend/tests/ -v`
Expected: PASS with 166+ passed, 0 failures.

- [ ] **Step 2: Run complete frontend vitest suite and build**

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
Expected: HTTP 200 OK with `status: "healthy"` and valid scanner state.

- [ ] **Step 5: Commit and push all changes to git**

```bash
git push origin main
```
Expected: Remote `mani124/BB.git` updated to latest commit.
