# Design Specification: Slippage Tracking, Regulatory Charges Engine & Setup-Filtered Journal

- **Date:** 2026-10-10
- **Status:** Proposed
- **Author:** Antigravity & User Pair
- **Target Repository:** `/Users/manigopal/Documents/BB_OPTIONS_DASHBOARD`

---

## 1. Executive Summary & Goals

This specification details the design for introducing **Realistic Execution Slippage Modeling**, the **Official Indian NSE/Dhan F&O Regulatory Charges Engine**, and **Setup-Filtered Trade Journaling** into the Bollinger Bands Options Trading Dashboard PRO.

### Primary Objectives:
1. **Per-Trade & Cumulative Slippage Tracking**:
   * Measure the exact point difference and monetary erosion between theoretical signal/trigger prices and actual execution fills using live order-book Bid/Ask quotes and tick latency.
   * Provide granular visibility into slippage on every individual trade and aggregated across the whole portfolio.
2. **Official F&O Regulatory & Brokerage Charges Engine**:
   * Implement accurate statutory tax and brokerage calculations matching Dhan HQ's official cost structure (revised post-SEBI October 2024 directives): flat ₹20/order brokerage, 0.1% STT on sell option premium, 0.05% NSE exchange turnover charges, 18% GST, 0.003% stamp duty, and SEBI turnover fees.
   * Compute true **Gross Realized P&L**, **Total Charges**, and **Net Realized P&L** for every trade.
3. **Setup-Filtered Closed Trades Journal**:
   * Add intuitive filter tabs above the Closed Trades table allowing one-click filtering by strategy (All, Setup 1: Squeeze, Setup 2: Walking Bands, Setup 3: W/M Reversal, Setup 4: ORB, Setup 5: Option Chart Breakout).
   * Display filtered win rates, total P&L, and average slippage per setup to isolate strategy performance.

---

## 2. Mathematical Modeling & Formulas

### 2.1 Slippage Formulation
When a signal is detected or an exit condition is met, market orders in live trading execute at the prevailing book quotes rather than theoretical trigger levels.

#### A. Entry Slippage (Buying Calls or Puts)
* Let $P_{\text{signal}}$ be the theoretical entry price recommended by the strategy.
* Let $P_{\text{ask}}$ be the prevailing best Ask price from the live option quote. If $P_{\text{ask}} \le 0$ (e.g. illiquid or offline), execution fills at the latest LTP plus a conservative 0.1% tick latency penalty.
* **Actual Entry Price**: $P_{\text{fill\_entry}} = P_{\text{ask}}$
* **Entry Slippage (Points)**:
  $$\Delta_{\text{entry}} = \max\left(0.0, P_{\text{fill\_entry}} - P_{\text{signal}}\right)$$

#### B. Exit Slippage (Closing on TP1, TP2, Trailed SL, or Hard SL)
* Let $P_{\text{trigger}}$ be the planned exit level (e.g. Target 1, Target 2, or Trailed Stop-Loss).
* Let $P_{\text{bid}}$ be the prevailing best Bid price from the live option quote. If $P_{\text{bid}} \le 0$, execution fills at the tick LTP minus a conservative 0.1% tick latency penalty.
* **Actual Exit Price**: $P_{\text{fill\_exit}} = P_{\text{bid}}$
* **Exit Slippage (Points)**:
  $$\Delta_{\text{exit}} = \max\left(0.0, P_{\text{trigger}} - P_{\text{fill\_exit}}\right)$$

#### C. Per-Trade Monetary Slippage Loss
$$\text{Slippage Cost (₹)} = (\Delta_{\text{entry}} + \Delta_{\text{exit}}) \times Q$$
Where $Q$ is the total executed contract quantity ($\text{Lots} \times \text{Lot Size}$).

#### D. Portfolio Cumulative Slippage Metrics
* **Total Portfolio Slippage (₹)**: $\sum_{i=1}^{N} \text{Slippage Cost}_i$
* **Average Slippage Points per Trade**: $\frac{1}{N} \sum_{i=1}^{N} (\Delta_{\text{entry}, i} + \Delta_{\text{exit}, i})$
* **Slippage Drag %**: $\frac{\text{Total Slippage (₹)}}{\text{Gross Winning P\&L (₹)}} \times 100$

---

### 2.2 Dhan HQ F&O Regulatory Charges Model
Calculates exact exchange, broker, and statutory taxes on NSE Option trades based on the October 2024 revised schedule.

#### Turnover Definitions
* **Buy Turnover**: $T_{\text{buy}} = P_{\text{fill\_entry}} \times Q$
* **Sell Turnover**: $T_{\text{sell}} = P_{\text{fill\_exit}} \times Q$
* **Total Turnover**: $T_{\text{total}} = T_{\text{buy}} + T_{\text{sell}}$

#### Tax & Fee Schedule
1. **Brokerage**:
   * Flat ₹20 per executed order leg.
   * Standard Round-Trip: 2 orders (1 Buy, 1 Sell) = ₹40.
   * Partial Profit Booking (TP1 half lots + TP2 runner lots): 3 orders (1 Buy, 2 Sells) = ₹60.
   $$\text{Brokerage} = N_{\text{orders}} \times 20.00$$
2. **STT (Securities Transaction Tax)**:
   * Charged strictly on the **Sell** side of option premium turnover at $0.10\%$ ($0.001$):
   $$\text{STT} = \text{round}\left(T_{\text{sell}} \times 0.0010\right)$$
3. **NSE Exchange Turnover Charges**:
   * Charged at $0.05\%$ ($0.0005$) on total premium turnover:
   $$\text{Exchange Fee} = T_{\text{total}} \times 0.0005$$
4. **SEBI Turnover Charges**:
   * Flat ₹10 per crore ($0.000001$):
   $$\text{SEBI Fee} = T_{\text{total}} \times 0.000001$$
5. **Stamp Duty**:
   * Charged strictly on the **Buy** side turnover at $0.003\%$ ($0.00003$):
   $$\text{Stamp Duty} = \text{round}\left(T_{\text{buy}} \times 0.00003\right)$$
6. **GST (Goods and Services Tax)**:
   * Standard $18\%$ on the sum of Brokerage, Exchange Turnover Charges, and SEBI Charges:
   $$\text{GST} = (\text{Brokerage} + \text{Exchange Fee} + \text{SEBI Fee}) \times 0.18$$

#### Net Realized P&L
$$\text{Total Charges} = \text{Brokerage} + \text{STT} + \text{Exchange Fee} + \text{SEBI Fee} + \text{Stamp Duty} + \text{GST}$$
$$\text{Gross Realized P\&L} = (P_{\text{fill\_exit}} - P_{\text{fill\_entry}}) \times Q$$
$$\textbf{Net Realized P\&L} = \text{Gross Realized P\&L} - \text{Total Charges}$$

---

## 3. System Architecture & Component Design

```
+--------------------------------------------------------------------------+
|                        Live Market Feed & Worker                         |
|   (Dhan WebSocket Ticker/Quote & HTTP Quotes: LTP, Bid, Ask, Volume)     |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                     PaperTrader (paper_trader.py)                        |
|  - Fill Engine: uses live Ask on entry, live Bid on exit                 |
|  - Tracks theoretical trigger vs actual fill                             |
|  - Computes slippage points & slippage ₹                                 |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|              Charges Calculator (charges_calculator.py)                  |
|  - Pure functional cost engine                                           |
|  - Computes: Brokerage, STT, NSE Fee, GST, Stamp Duty, SEBI, Net P&L     |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|               SQLite Trade Journal (backend/data/trades.db)              |
|  - Stores execution details, slippage fields, and tax breakdowns         |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|             Frontend React View (PaperPortfolioView.tsx)                 |
|  - 4-Card Hero Bar: Gross P&L | Slippage | Charges | Net Realized P&L    |
|  - Setup Filter Tabs: All | Setup 1 | Setup 2 | Setup 3 | Setup 4 | 5    |
|  - Trade Row Popover / Tooltip: Full itemized tax receipt & slippage pts |
+--------------------------------------------------------------------------+
```

### 3.1 New Module: `backend/app/services/charges_calculator.py`
A stateless, highly testable module providing:
* `TradeChargesBreakdown`: Pydantic model encapsulating `brokerage`, `stt`, `exchange_fee`, `gst`, `stamp_duty`, `sebi_fee`, `total_charges`.
* `calculate_option_trade_charges(buy_price, sell_price, quantity, orders_count, brokerage_per_order=20.0) -> TradeChargesBreakdown`.

### 3.2 Updates to `PaperPosition` Model
Add the following fields to `PaperPosition`:
* `theoretical_entry_price: float` (original signal price)
* `entry_slippage_points: float` ($P_{\text{fill\_entry}} - P_{\text{theoretical\_entry}}$)
* `theoretical_exit_price: Optional[float]` (target or SL trigger level)
* `exit_slippage_points: float` ($P_{\text{theoretical\_exit}} - P_{\text{fill\_exit}}$)
* `total_slippage_cost: float` (total monetary slippage in ₹)
* `gross_pnl: float` (pure price difference $\times$ quantity)
* `charges_breakdown: Optional[TradeChargesBreakdown]`
* `total_charges: float`
* `net_pnl: float` (`gross_pnl - total_charges`)

### 3.3 Updates to `PaperPortfolio` Model
Add aggregate metrics:
* `total_gross_pnl: float`
* `total_slippage_cost: float`
* `avg_slippage_points: float`
* `total_charges: float`
* `total_net_pnl: float`

### 3.4 Database Persistence (`backend/app/services/paper_trader.py`)
Update SQLite database table `trades` schema to persist:
* `theoretical_entry REAL DEFAULT 0.0`
* `entry_slippage REAL DEFAULT 0.0`
* `theoretical_exit REAL DEFAULT 0.0`
* `exit_slippage REAL DEFAULT 0.0`
* `total_slippage_cost REAL DEFAULT 0.0`
* `gross_pnl REAL DEFAULT 0.0`
* `total_charges REAL DEFAULT 0.0`
* `net_pnl REAL DEFAULT 0.0`
* `charges_json TEXT DEFAULT ''`
Use backward-compatible `ALTER TABLE ADD COLUMN` migration upon engine startup if columns are missing.

---

## 4. Setup-Filtered Trade Journal Specification

### 4.1 Filter Options
In `PaperPortfolioView.tsx`, above the closed trades table, provide a filter pill selector:
1. **All Setups** (default): Shows all completed trades.
2. **Setup 1 (Squeeze)**: Filters trades where `setup_type == "SETUP_1_SQUEEZE_EXPANSION"`.
3. **Setup 2 (Walking Bands)**: Filters trades where `setup_type == "SETUP_2_WALKING_BANDS"`.
4. **Setup 3 (W/M Reversal)**: Filters trades where `setup_type == "SETUP_3_WM_REVERSAL"`.
5. **Setup 4 (ORB 9:30 AM)**: Filters trades where `setup_type == "SETUP_4_OPENING_RANGE_BREAKOUT"`.
6. **Setup 5 (Option Chart)**: Filters trades where `setup_type == "SETUP_5_OPTION_CHART_BREAKOUT"`.

### 4.2 Dynamic Setup Summary Strip
When a specific setup is filtered, the header bar dynamically updates to display that setup's isolated performance:
* **Filtered Trades**: e.g. `12 Trades`
* **Setup Win Rate**: e.g. `75.0%`
* **Setup Gross P&L**: e.g. `+₹6,420`
* **Setup Net P&L**: e.g. `+₹5,890`
* **Avg Slippage**: e.g. `-0.75 pts`

---

## 5. UI / UX Design

### 5.1 Portfolio Hero Header
Four prominent glassmorphism cards at the top of the Paper Trading tab:
1. **Gross Realized P&L**: Large green/rose currency display (`+₹12,450.00`).
2. **Slippage Impact**: Amber/rose indicator displaying total points lost and rupee value (`-14.2 pts (-₹923.00)`), with an info badge showing `Avg: -0.8 pts/trade`.
3. **Brokerage & Statutory Taxes**: Muted slate/cyan card showing total deductions (`-₹642.50`), with order count.
4. **Net Realized P&L**: Highlighted primary performance metric (`+₹10,884.50`) reflecting exact take-home forward-testing profit.

### 5.2 Closed Trade Row & Popover
* In the **Closed Trades** table:
  * Column for **Entry / Fill**: Shows `₹145.00` with small subtext `(Slippage: +0.80 pts)`.
  * Column for **Exit / Fill**: Shows `₹180.00` with small subtext `(Slippage: -0.50 pts)`.
  * Column for **Gross vs Net P&L**: Shows `+₹2,275 Gross` and `+₹2,192 Net`.
  * An interactive **"Receipt / Tax Breakdown" icon**: Hovering/clicking triggers a clean popover with:
    * Brokerage: ₹40.00
    * STT (0.1%): ₹23.40
    * NSE Turnover Fee: ₹10.56
    * GST (18%): ₹9.10
    * Stamp Duty: ₹0.30
    * SEBI Charges: ₹0.02
    * Total Deducted: ₹83.38

---

## 6. Testing & Verification Strategy

Following Test-Driven Development (TDD):
1. **Charges Calculator Unit Tests (`test_charges_calculator.py`)**:
   * Verify standard round-trip trade: 1 Buy @ 100, 1 Sell @ 150, Qty 65 (Nifty lot).
     - Buy turnover: 6,500. Sell turnover: 9,750. Total: 16,250.
     - Brokerage: ₹40.00.
     - STT: $\text{round}(9750 \times 0.001) = ₹9.75 \to ₹10.00$.
     - Exchange fee: $16250 \times 0.0005 = ₹8.125$.
     - GST: $(40 + 8.125 + 0.016) \times 0.18 = ₹8.665$.
     - Stamp duty: $\text{round}(6500 \times 0.00003) = ₹0.20$.
     - Assert exact sums match expected totals within $\pm ₹0.05$.
   * Verify partial booking (3 order legs = ₹60 brokerage).
2. **Slippage Simulation Tests (`test_paper_slippage.py`)**:
   * Assert position opened with Ask > Signal records `entry_slippage_points > 0`.
   * Assert position closed on Bid < Target records `exit_slippage_points > 0` and calculates `total_slippage_cost`.
3. **Database Migration & Backward Compatibility Tests**:
   * Verify opening existing `trades.db` without new columns auto-migrates cleanly without crashing or corrupting historic records.
4. **Frontend Component Tests (`PaperPortfolioView.test.tsx`)**:
   * Test Setup filter tab clicks accurately filter the rows.
   * Test Gross vs Net P&L display and charges breakdown tooltip rendering.
   * Full TypeScript compilation check (`npm run build`).

---

## 7. Security & Zero-Token Compliance
* Slippage and charges calculations run entirely locally with zero external network requests.
* No credentials, account tokens, or client IDs are logged or stored in trade database records.
