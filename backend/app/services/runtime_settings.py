"""Runtime-adjustable settings: every risk limit, quality guard, telemetry switch and earnings-strategy
parameter lives here, not in code.

Resolution order for a key: a value saved from the dashboard (stored in the database, survives restarts)
-> the environment default read through ``app.core.config.settings`` (or the definition's own default).
Nothing here is cached beyond the process: a changed value applies to the next decision, no restart.

Each change is validated (type, range, choices) and written to an audit trail with the old and new value.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.core.config import settings as env_settings
from app.services import market_hours
from app.services import db

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass(frozen=True)
class SettingDef:
    key: str
    label: str
    group: str
    type: str  # "int" | "float" | "bool" | "str" | "time"
    description: str
    default: Any = None
    env_attr: Optional[str] = None  # read the default from app.core.config.settings.<env_attr> when present
    unit: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    choices: tuple = ()
    zero_disables: bool = False  # 0 means "off" for this limit; shown in the UI

    def default_value(self) -> Any:
        if self.env_attr and hasattr(env_settings, self.env_attr):
            return getattr(env_settings, self.env_attr)
        return self.default


def _d(**kw) -> SettingDef:
    return SettingDef(**kw)


# ----------------------------------------------------------------------------------------------------
# Registry. Add a definition here and it appears in the API and the Settings tab with validation and audit.
# ----------------------------------------------------------------------------------------------------
G_RISK = "Risk limits (RMS)"
G_SIZE = "Position sizing"
G_QUALITY = "Entry quality guards"
G_TELE = "Telemetry"
G_EARN = "Earnings options strategy"
G_LIVE = "Live broker routing"
G_REC = "Market data recorder"
G_SWING = "Swing equity book (Setup 15)"
G_S16 = "Option squeeze breakout (Setup 16)"

DEFINITIONS: tuple[SettingDef, ...] = (
    # ---- RMS ----
    _d(key="daily_loss_limit", label="Daily loss limit", group=G_RISK, type="float", unit="INR",
       description="New entries stop for the rest of the IST day once the day's net P&L reaches minus this amount. "
                   "It is checked separately for the main options setups, for Setup 11 and for the earnings book, so the "
                   "most all paper books together can lose in a day is about three times this.",
       env_attr="DAILY_LOSS_LIMIT", min=0, zero_disables=True),
    _d(key="max_open_positions", label="Max open positions", group=G_RISK, type="int",
       description="Most positions that may be open at once in one book.", env_attr="MAX_OPEN_POSITIONS",
       min=0, zero_disables=True),
    _d(key="max_open_notional", label="Max open premium", group=G_RISK, type="float", unit="INR",
       description="Cap on total entry premium (price x quantity) across open positions in one book.",
       env_attr="MAX_OPEN_NOTIONAL", min=0, zero_disables=True),
    _d(key="max_entries_per_symbol_per_day", label="Max entries per symbol per day", group=G_RISK, type="int",
       description="Most entries allowed in one underlying per IST day.", env_attr="MAX_ENTRIES_PER_SYMBOL_PER_DAY",
       min=0, zero_disables=True),
    _d(key="max_entries_per_day", label="Max entries per day (all symbols)", group=G_RISK, type="int",
       description="Most new entries allowed in one book per IST day, across every symbol.", default=0,
       min=0, zero_disables=True),
    _d(key="max_lots_per_trade", label="Max lots per trade", group=G_RISK, type="int", unit="lots",
       description="Hard ceiling on lots in any single entry, applied after the risk-based sizing.", default=0,
       min=0, zero_disables=True),
    _d(key="max_consecutive_losses", label="Pause after consecutive losses", group=G_RISK, type="int",
       description="After this many losing trades in a row today, new entries in that book pause until a winning trade closes or the next IST day.",
       default=0, min=0, zero_disables=True),
    _d(key="reentry_cooldown_seconds", label="Re-entry cooldown", group=G_RISK, type="int", unit="seconds",
       description="Wait after an exit before re-entering the same stock and side.", env_attr="REENTRY_COOLDOWN_SECONDS",
       min=0, zero_disables=True),
    # ---- sizing ----
    _d(key="default_lots", label="Default lots", group=G_SIZE, type="int", unit="lots",
       description="Lots per auto entry before the risk cap trims it (minimum 2 so Target 1 can book half).",
       default=2, min=2),
    _d(key="max_risk_per_trade", label="Max risk per trade", group=G_SIZE, type="float", unit="INR",
       description="Entry to stop distance x quantity may not exceed this; lots are trimmed or the trade skipped.",
       default=8000.0, min=500),
    # ---- quality ----
    _d(key="max_quote_age_seconds", label="Max quote age", group=G_QUALITY, type="float", unit="seconds",
       description="Live entries are refused when the option quote is older than this.",
       env_attr="MAX_QUOTE_AGE_SECONDS", min=0, zero_disables=True),
    _d(key="max_entry_spread_pct", label="Max entry spread", group=G_QUALITY, type="float", unit="%",
       description="Live entries are refused when (ask - bid) / ask is wider than this.",
       env_attr="MAX_ENTRY_SPREAD_PCT", min=0, max=100, zero_disables=True),
    _d(key="gap_exit_pct", label="Gap-exit label threshold", group=G_QUALITY, type="float", unit="%",
       description="A stop or target fill this far beyond its level is labelled a gap exit.",
       env_attr="GAP_EXIT_PCT", min=0, max=100, zero_disables=True),
    # ---- telemetry ----
    _d(key="telemetry_enabled", label="Record telemetry", group=G_TELE, type="bool",
       description="Master switch for decision, error and excursion recording.", default=True),
    _d(key="telemetry_jsonl_enabled", label="Mirror telemetry to JSONL files", group=G_TELE, type="bool",
       description="Also append each record to <data dir>/logs/*.jsonl for pandas / notebooks.", default=True),
    _d(key="telemetry_skip_logging", label="Record skipped signals", group=G_TELE, type="bool",
       description="Log every signal the engine declines, with the reason. Turn off to keep only entries and exits.",
       default=True),
    _d(key="telemetry_retention_days", label="Telemetry retention", group=G_TELE, type="int", unit="days",
       description="Decision and error rows older than this are deleted. 0 keeps everything.", default=90,
       min=0, zero_disables=True),
    _d(key="telemetry_excursion_flush_seconds", label="Excursion save interval", group=G_TELE, type="int",
       unit="seconds", description="How often running MFE / MAE values are written to the database.", default=15, min=1),
    # ---- market data recorder (market_recorder.py) ----
    _d(key="recorder_enabled", label="Record market bars", group=G_REC, type="bool",
       description="Save every completed 5m/15m bar the scanner sees (real data only) to market_bars.db, so setup "
                   "ideas and variants can be tested offline.", default=True),
    _d(key="recorder_retention_days", label="Bar retention", group=G_REC, type="int", unit="days",
       description="Bars older than this are deleted at startup. 0 keeps everything.", default=180, min=0,
       zero_disables=True),
    # ---- live broker routing (order_router.py). Mode and arming are NOT settings: see /api/live. ----
    _d(key="live_allowed_setups", label="Setups allowed to route", group=G_LIVE, type="str",
       description="Setup numbers whose entries may be sent to the broker, comma separated (for example 5 or 12). "
                   "Empty routes nothing. Start with one. Two routed setups never hold the same contract, so the "
                   "second entry on a contract is refused.", default=""),
    _d(key="live_max_lots_per_order", label="Max lots per order", group=G_LIVE, type="int", unit="lots",
       description="An entry above this many lots is refused, not trimmed (the paper position keeps its size).",
       default=2, min=1, max=100),
    _d(key="live_max_order_value", label="Max value per entry order", group=G_LIVE, type="float", unit="INR",
       description="Quantity x limit price may not exceed this.", default=150000.0, min=1),
    _d(key="live_max_entries_per_day", label="Max entry orders per day", group=G_LIVE, type="int",
       description="Most entry orders sent in one IST day. Exits are never counted or blocked.", default=6, min=1),
    _d(key="live_max_orders_per_day", label="Max orders per day (all)", group=G_LIVE, type="int",
       description="Circuit breaker on every order sent in one IST day. Past it new entries stop; exits still go.",
       default=40, min=1),
    _d(key="live_max_open_positions", label="Max open live positions", group=G_LIVE, type="int",
       description="Entries are refused while this many routed positions are open.", default=2, min=1),
    _d(key="live_daily_loss_limit", label="Live daily loss limit", group=G_LIVE, type="float", unit="INR",
       description="Entries stop once today's routed P&L reaches minus this. 0 uses the general daily loss limit; "
                   "if both are 0 live entries are refused.", default=0.0, min=0),
    _d(key="live_entry_order_type", label="Entry order type", group=G_LIVE, type="str",
       description="LIMIT places at the ask plus the buffer below. MARKET is not recommended for options.",
       default="LIMIT", choices=("LIMIT", "MARKET")),
    _d(key="live_entry_limit_buffer_pct", label="Entry limit buffer", group=G_LIVE, type="float", unit="%",
       description="A LIMIT entry is priced this far above the ask so it fills but cannot chase far.",
       default=1.0, min=0, max=10),
    _d(key="live_exit_order_type", label="Exit order type", group=G_LIVE, type="str",
       description="LIMIT is priced from the live bid (else the last trade) minus the buffer; if it does not fill it is "
                   "cancelled and re-sent from a fresh quote with a wider buffer each time (brokers and exchanges often "
                   "refuse plain MARKET orders on options). MARKET gets out for sure where allowed.",
       default="LIMIT", choices=("MARKET", "LIMIT")),
    _d(key="live_exit_limit_buffer_pct", label="Exit limit buffer", group=G_LIVE, type="float", unit="%",
       description="A LIMIT exit is priced this far below the bid. Each unfilled attempt adds this much again, "
                   "up to 20%.", default=2.0, min=0, max=20),
    _d(key="live_product_type", label="Product type", group=G_LIVE, type="str",
       description="INTRADAY squares off at the broker's cutoff; NORMAL carries overnight.",
       default="INTRADAY", choices=("INTRADAY", "NORMAL")),
    _d(key="live_algo_id", label="Algo ID", group=G_LIVE, type="str",
       description="The algo identifier your broker registered for this strategy (Definedge refuses orders without it). "
                   "Empty refuses every live order.", default=""),
    _d(key="live_order_timeout_seconds", label="Fill wait", group=G_LIVE, type="int", unit="seconds",
       description="How long to wait for an order to fill before cancelling an entry's unfilled part.",
       default=15, min=3, max=120),
    _d(key="live_reconcile_seconds", label="Reconcile interval", group=G_LIVE, type="int", unit="seconds",
       description="How often routed orders and positions are checked against the broker while anything is routed.",
       default=30, min=10, max=600),
    _d(key="live_halt_on_mismatch", label="Halt entries on position mismatch", group=G_LIVE, type="bool",
       description="Stop new entries when the broker's positions differ from what the router expects, until you resume.",
       default=True),
    # ---- earnings strategy ----
    _d(key="earnings_enabled", label="Earnings strategy enabled", group=G_EARN, type="bool",
       description="Allow the earnings paper book to open new positions.", default=False),
    _d(key="earnings_mode_a_enabled", label="Mode A (pre-earnings straddle)", group=G_EARN, type="bool",
       description="Buy an ATM straddle ahead of earnings to capture IV expansion.", default=True),
    _d(key="earnings_mode_b_enabled", label="Mode B (post-earnings iron condor)", group=G_EARN, type="bool",
       description="Sell a defined-risk iron condor the day before earnings to capture the IV crush.", default=True),
    _d(key="earnings_mode_a_far_days", label="Mode A: entry window opens", group=G_EARN, type="int", unit="days before",
       description="Window opens when earnings are this many calendar days away (inclusive).", default=12, min=1, max=60),
    _d(key="earnings_mode_a_near_days", label="Mode A: entry window closes", group=G_EARN, type="int", unit="days before",
       description="Window closes when earnings are this many calendar days away (inclusive).", default=8, min=1, max=60),
    _d(key="earnings_mode_a_exit_days_before", label="Mode A: exit before earnings", group=G_EARN, type="int",
       unit="trading days", description="Exit this many trading days before the announcement.", default=1, min=1, max=10),
    _d(key="earnings_mode_a_max_loss_pct", label="Mode A: stop loss", group=G_EARN, type="float", unit="% of premium",
       description="Exit when the straddle has lost this share of its entry premium. 0 disables.", default=40.0,
       min=0, max=100, zero_disables=True),
    _d(key="earnings_mode_a_max_ivp", label="Mode A: max IV percentile", group=G_EARN, type="float", unit="%",
       description="Only buy volatility when the stock's IV percentile is at or below this. 0 disables the filter.",
       default=40.0, min=0, max=100, zero_disables=True),
    _d(key="earnings_mode_b_min_ivr", label="Mode B: min IV rank", group=G_EARN, type="float", unit="%",
       description="Only sell the condor when IV rank is at or above this. 0 disables the filter.", default=0.0,
       min=0, max=100, zero_disables=True),
    _d(key="earnings_condor_short_steps", label="Condor: short strikes from ATM", group=G_EARN, type="int",
       unit="strike steps", description="Distance of the short call and put from the at-the-money strike.",
       default=2, min=1, max=20),
    _d(key="earnings_condor_wing_steps", label="Condor: wing width", group=G_EARN, type="int", unit="strike steps",
       description="Distance of each protective long strike beyond its short strike.", default=2, min=1, max=20),
    _d(key="earnings_min_condor_credit", label="Condor: minimum net credit", group=G_EARN, type="float", unit="INR/unit",
       description="Skip the condor when the net credit per unit is at or below this.", default=0.0, min=0),
    _d(key="earnings_min_days_to_expiry", label="Min days to expiry at exit", group=G_EARN, type="int", unit="days",
       description="Force exit (and roll contract selection to next month) inside this many calendar days of expiry, "
                   "to stay clear of physical settlement.", default=7, min=0, max=30),
    _d(key="earnings_max_positions", label="Max open earnings positions", group=G_EARN, type="int",
       description="Most positions open at once in the earnings book.", default=4, min=1),
    _d(key="earnings_lots", label="Lots per position", group=G_EARN, type="int", unit="lots",
       description="Lots traded per earnings position.", default=1, min=1),
    _d(key="earnings_max_capital_per_trade", label="Max capital per position", group=G_EARN, type="float", unit="INR",
       description="Skip a candidate whose premium paid (A) or max risk (B) exceeds this. 0 disables.", default=0.0,
       min=0, zero_disables=True),
    _d(key="earnings_max_spread_pct", label="Max option spread", group=G_EARN, type="float", unit="%",
       description="Skip when any leg's bid / ask spread is wider than this share of its mid price. 0 disables.",
       default=25.0, min=0, max=100, zero_disables=True),
    _d(key="earnings_one_per_sector", label="One position per sector", group=G_EARN, type="bool",
       description="Refuse a new position in a sector that already has one open.", default=True),
    _d(key="earnings_entry_time", label="Entry time", group=G_EARN, type="time", unit="IST",
       description="Do not open earnings positions before this time of day.", default="15:00"),
    _d(key="earnings_exit_time", label="Mode A: exit time", group=G_EARN, type="time", unit="IST",
       description="Time of day the pre-earnings straddle is closed on its exit date.", default="15:15"),
    _d(key="earnings_mode_b_exit_time", label="Mode B: exit time", group=G_EARN, type="time", unit="IST",
       description="Time of day on the reaction day when the condor is closed (after the IV crush).", default="09:20"),
    _d(key="earnings_default_session", label="Unspecified announcement session", group=G_EARN, type="str",
       description="How to treat calendar rows with no session: BMO (before market open), AMC (after market close) "
                   "or SKIP (do not trade them).", default="SKIP", choices=("BMO", "AMC", "SKIP")),
    _d(key="earnings_iv_lookback_days", label="IV history window", group=G_EARN, type="int", unit="days",
       description="Days of stored at-the-money IV used for IV percentile and IV rank.", default=252, min=20, max=2000),
    _d(key="earnings_iv_min_history", label="IV history required", group=G_EARN, type="int", unit="days",
       description="Minimum stored days before IV percentile / rank is trusted.", default=20, min=2, max=2000),
    _d(key="earnings_iv_missing_policy", label="When IV history is too short", group=G_EARN, type="str",
       description="allow: trade without the IV filter (logged); skip: do not trade the stock yet.",
       default="allow", choices=("allow", "skip")),
    _d(key="earnings_auto_sync", label="Auto-fill calendar from NSE", group=G_EARN, type="bool",
       description="Once a day, add F&O stocks with a board meeting for financial results from the NSE event calendar. "
                   "Rows you add or edit by hand are never overwritten.", default=True),
    _d(key="earnings_sync_horizon_days", label="Calendar look-ahead", group=G_EARN, type="int", unit="days",
       description="How far ahead the NSE sync adds earnings dates.", default=45, min=7, max=180),
    _d(key="earnings_poll_seconds", label="Strategy check interval", group=G_EARN, type="int", unit="seconds",
       description="How often the earnings book scans, marks and exits positions while the market is open.",
       default=60, min=15, max=3600),
    _d(key="earnings_starting_capital", label="Starting paper capital", group=G_EARN, type="float", unit="INR",
       description="Capital the earnings paper book reports returns against.", default=500000.0, min=0),
    # ---- Setup 16 (setup16.py) ----
    _d(key="setup16_stop_pct", label="Setup 16 max stop distance", group=G_S16, type="float", unit="% below entry",
       description="The stop is the nearer of the option's lower Bollinger Band and this percentage below the entry. "
                   "After a breakout the lower band is often 30-50% under the price; this keeps the risk inside the cap.",
       default=12.0, min=4, max=40),
    _d(key="setup16_window_start", label="Setup 16 first entry bar", group=G_S16, type="time", unit="IST",
       description="Earliest 5m bar start that may produce a Setup 16 entry.", default="09:30"),
    _d(key="setup16_window_end", label="Setup 16 last entry bar", group=G_S16, type="time", unit="IST",
       description="Latest 5m bar start that may produce a Setup 16 entry. Mid-morning entries lost heavily on 2026-10-19; "
                   "narrow the window here if that repeats.", default="14:25"),
    _d(key="watchlist_enabled", label="After-close watchlist", group=G_S16, type="bool",
       description="After the close, screen the F&O stocks on daily charts for a squeeze and let the scanner check the "
                   "qualifying stocks for Setup 16 (and only Setup 16) the next trading day. Needs a Dhan login after the close.",
       default=True),
    _d(key="watchlist_size", label="Watchlist size", group=G_S16, type="int", unit="stocks",
       description="Most stocks kept on tomorrow's watchlist, tightest squeeze first.", default=40, min=1, max=100),
    _d(key="watchlist_bw_percentile", label="Squeeze: BandWidth percentile", group=G_S16, type="float", unit="%",
       description="A stock qualifies when its daily BandWidth (20, 2) is within this lowest share of its last 120 days.",
       default=20.0, min=1, max=50),
    _d(key="watchlist_use_nr7", label="Squeeze: count NR7 days", group=G_S16, type="bool",
       description="Also qualify a stock whose last day had the narrowest high-low range of the last 7 days.", default=True),
    _d(key="watchlist_min_avg_value_cr", label="Minimum average traded value", group=G_S16, type="float", unit="INR crore",
       description="Liquidity filter: 20-day average of close x volume of the stock, a proxy for liquid options.",
       default=50.0, min=0),
    _d(key="watchlist_build_time", label="Build time", group=G_S16, type="time", unit="IST",
       description="After this time on a trading day (the daily bar is final) the watchlist for the next trading day is built, once, as "
                   "soon as a Dhan login exists. A missed build is retried every 10 minutes, and a login or restart before "
                   "the close still gets a list for today built from yesterday's bars.", default="16:15"),
    # ---- swing equity book (swing_engine.py / swing_signals.py) ----
    _d(key="swing_enabled", label="Swing book enabled", group=G_SWING, type="bool",
       description="Allow the swing paper book to queue new daily-bar entries. Open positions are always managed.", default=False),
    _d(key="swing_setup15_enabled", label="Setup 15 (ATR trend flip)", group=G_SWING, type="bool",
       description="Daily Supertrend flips from down to up: buy the next open, trail the stop on the Supertrend line.", default=True),
    _d(key="swing_atr_period", label="Supertrend ATR period", group=G_SWING, type="int", unit="days",
       description="ATR length of the daily Supertrend. 3 with a multiplier of 1 is the swing-length variant in the only "
                   "Indian study found (about 15-day holds); 10 / 3 trends for months.", default=3, min=2, max=50),
    _d(key="swing_atr_mult", label="Supertrend multiplier", group=G_SWING, type="float", unit="x ATR",
       description="Band distance in ATRs. Smaller flips and stops out faster.", default=1.0, min=0.5, max=6),
    _d(key="swing_exit_mode", label="Exit mode", group=G_SWING, type="str",
       description="stop: the Supertrend line is a stop order, hit the moment price trades through it (conservative, "
                   "stops out on wicks). close: exit at the next open after a close beyond the line, as the Indian study did; "
                   "only the max-loss stop below protects the position inside a day.", default="stop", choices=("stop", "close")),
    _d(key="swing_close_mode_max_loss_pct", label="Close mode: max-loss stop", group=G_SWING, type="float", unit="% below entry",
       description="In close exit mode, an intraday stop this far below the entry price caps a bad day. Also limits the "
                   "distance used to size the position.", default=8.0, min=1, max=30),
    _d(key="swing_sma_filter_days", label="Trend filter (close above SMA)", group=G_SWING, type="int", unit="days",
       description="Only buy when the close is above this simple moving average. 0 turns the filter off.", default=200,
       min=0, max=400, zero_disables=True),
    _d(key="swing_min_price", label="Min price", group=G_SWING, type="float", unit="INR",
       description="Skip stocks closing below this price.", default=50.0, min=0),
    _d(key="swing_min_avg_volume", label="Min average volume", group=G_SWING, type="float", unit="shares",
       description="Skip stocks whose 20-day average daily volume is below this.", default=100000.0, min=0),
    _d(key="swing_max_hold_days", label="Max holding period", group=G_SWING, type="int", unit="trading days",
       description="Exit at the next open once a position has been held this many trading days. 0 = no time stop.",
       default=20, min=0, max=250, zero_disables=True),
    _d(key="swing_max_positions", label="Max open positions", group=G_SWING, type="int",
       description="Open plus queued swing positions at once.", default=5, min=1, max=50),
    _d(key="swing_max_new_per_day", label="Max new entries per day", group=G_SWING, type="int",
       description="Entries queued from one day's close. 0 = no cap beyond the position limit.", default=3, min=0, zero_disables=True),
    _d(key="swing_risk_per_trade", label="Risk per trade", group=G_SWING, type="float", unit="INR",
       description="Quantity = this / (entry - stop), capped by the capital limit below.", default=5000.0, min=100),
    _d(key="swing_max_capital_per_trade", label="Max capital per position", group=G_SWING, type="float", unit="INR",
       description="Largest entry value (price x quantity) in one position.", default=100000.0, min=1000),
    _d(key="swing_slippage_bps", label="Slippage per side", group=G_SWING, type="float", unit="bps",
       description="Added to buys and taken off sells on top of the open / stop price. An assumption: compare with real fills before trusting results.",
       default=10.0, min=0, max=200),
    _d(key="swing_brokerage_per_order", label="Brokerage per order", group=G_SWING, type="float", unit="INR",
       description="Delivery brokerage per leg. 0 matches the discount-broker schedule; confirm your broker's.", default=0.0, min=0),
    _d(key="swing_dp_charge", label="DP charge per sell day", group=G_SWING, type="float", unit="INR",
       description="Depository charge on each delivery sale (includes GST).", default=15.34, min=0),
    _d(key="swing_earnings_blackout_days", label="Earnings blackout", group=G_SWING, type="int", unit="calendar days",
       description="Skip entries when the earnings calendar lists results within this many days. 0 = off.", default=5,
       min=0, max=30, zero_disables=True),
    _d(key="swing_scan_time", label="Daily scan time", group=G_SWING, type="time", unit="IST",
       description="After this time on a trading day the engine reads the finished daily bars, manages positions and scans.", default="16:00"),
    _d(key="swing_poll_seconds", label="Check interval", group=G_SWING, type="int", unit="seconds",
       description="How often the engine looks for a new finished trading day.", default=600, min=60, max=7200),
    _d(key="swing_starting_capital", label="Starting paper capital", group=G_SWING, type="float", unit="INR",
       description="Capital the swing paper book reports returns against.", default=1000000.0, min=0),
)

BY_KEY: dict[str, SettingDef] = {d.key: d for d in DEFINITIONS}


class SettingError(ValueError):
    pass


def coerce(defn: SettingDef, raw: Any) -> Any:
    """Validate and convert `raw` to the definition's type. Raises SettingError with a user-readable reason."""
    try:
        if defn.type == "bool":
            if isinstance(raw, bool):
                return raw
            s = str(raw).strip().lower()
            if s in ("1", "true", "yes", "on"):
                return True
            if s in ("0", "false", "no", "off"):
                return False
            raise SettingError(f"{defn.label}: expected true or false")
        if defn.type in ("int", "float"):
            if isinstance(raw, bool):
                raise SettingError(f"{defn.label}: expected a number")
            val: Any = float(raw)
            if val != val or val in (float("inf"), float("-inf")):
                raise SettingError(f"{defn.label}: expected a finite number")
            if defn.type == "int":
                if val != int(val):
                    raise SettingError(f"{defn.label}: expected a whole number")
                val = int(val)
            if val != val or val in (float("inf"), float("-inf")):
                raise SettingError(f"{defn.label}: expected a finite number")
            if defn.min is not None and val < defn.min:
                raise SettingError(f"{defn.label}: must be at least {defn.min:g}")
            if defn.max is not None and val > defn.max:
                raise SettingError(f"{defn.label}: must be at most {defn.max:g}")
            return val
        if defn.type == "time":
            s = str(raw).strip()
            if not _TIME_RE.match(s):
                raise SettingError(f"{defn.label}: expected HH:MM (24 hour)")
            return s
        s = str(raw).strip()
        if defn.choices and s not in defn.choices:
            raise SettingError(f"{defn.label}: must be one of {', '.join(defn.choices)}")
        return s
    except (TypeError, ValueError) as exc:
        if isinstance(exc, SettingError):
            raise
        raise SettingError(f"{defn.label}: invalid value {raw!r}") from exc


def _now() -> str:
    return market_hours.now_ist().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class RuntimeSettings:
    """Per-database settings store. `db_path=None` keeps values in memory only (engines built without storage)."""
    db_path: Optional[str] = None
    _overrides: dict[str, Any] = field(default_factory=dict)
    _hooks: dict[str, list[Callable[[Any], None]]] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.db_path:
            self._init_db()
            self._load()

    # ---- storage ----
    def _conn(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runtime_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT)")
            conn.execute("""CREATE TABLE IF NOT EXISTS settings_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, changed_at TEXT, key TEXT, old_value TEXT, new_value TEXT, actor TEXT)""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_settings_audit_key ON settings_audit(key, id)")

    def _load(self) -> None:
        with self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM runtime_settings").fetchall()
        for row in rows:
            defn = BY_KEY.get(row["key"])
            if defn is None:
                continue  # setting was removed in a newer release
            try:
                self._overrides[defn.key] = coerce(defn, row["value"])
            except SettingError:
                continue  # a stale or hand-edited value never blocks start-up; the default applies

    # ---- reads ----
    def get(self, key: str) -> Any:
        defn = BY_KEY[key]
        with self._lock:
            if key in self._overrides:
                return self._overrides[key]
        return coerce(defn, defn.default_value())

    def is_overridden(self, key: str) -> bool:
        with self._lock:
            return key in self._overrides

    def all(self) -> list[dict]:
        out = []
        for d in DEFINITIONS:
            out.append({
                "key": d.key, "label": d.label, "group": d.group, "type": d.type, "unit": d.unit,
                "description": d.description, "value": self.get(d.key),
                "default": coerce(d, d.default_value()), "overridden": self.is_overridden(d.key),
                "min": d.min, "max": d.max, "choices": list(d.choices), "zero_disables": d.zero_disables,
            })
        return out

    # ---- writes ----
    def on_change(self, key: str, fn: Callable[[Any], None]) -> None:
        """Call fn(new_value) after `key` changes (used to keep engine state that mirrors a setting in step)."""
        self._hooks.setdefault(key, []).append(fn)

    def set(self, key: str, raw: Any, actor: str = "dashboard") -> Any:
        defn = BY_KEY.get(key)
        if defn is None:
            raise SettingError(f"Unknown setting {key!r}")
        value = coerce(defn, raw)
        with self._lock:
            old = self.get(key)
            self._overrides[key] = value
            self._persist(key, value, old, actor)
        self._fire(key, value)
        return value

    def adopt(self, key: str, raw: Any) -> None:
        """Take over a value saved before this store existed: persisted but not audited as a user change."""
        defn = BY_KEY[key]
        value = coerce(defn, raw)
        with self._lock:
            self._overrides[key] = value
            if self.db_path:
                with self._conn() as conn:
                    conn.execute("INSERT OR REPLACE INTO runtime_settings (key, value, updated_at) VALUES (?,?,?)",
                                 (key, str(value), _now()))

    def reset(self, key: str, actor: str = "dashboard") -> Any:
        defn = BY_KEY.get(key)
        if defn is None:
            raise SettingError(f"Unknown setting {key!r}")
        with self._lock:
            old = self.get(key)
            self._overrides.pop(key, None)
            if self.db_path:
                with self._conn() as conn:
                    conn.execute("DELETE FROM runtime_settings WHERE key = ?", (key,))
                    conn.execute("INSERT INTO settings_audit (changed_at, key, old_value, new_value, actor) VALUES (?,?,?,?,?)",
                                 (_now(), key, str(old), "(default)", actor))
        value = self.get(key)
        self._fire(key, value)
        return value

    def set_many(self, changes: dict[str, Any], actor: str = "dashboard") -> dict[str, Any]:
        """Validate every change first so a bad value never leaves the batch half-applied."""
        cleaned = {}
        for k, v in changes.items():
            defn = BY_KEY.get(k)
            if defn is None:
                raise SettingError(f"Unknown setting {k!r}")
            cleaned[k] = coerce(defn, v)
        return {k: self.set(k, v, actor) for k, v in cleaned.items()}

    def _persist(self, key: str, value: Any, old: Any, actor: str) -> None:
        if not self.db_path:
            return
        with self._conn() as conn:
            conn.execute("INSERT OR REPLACE INTO runtime_settings (key, value, updated_at) VALUES (?,?,?)",
                         (key, str(value), _now()))
            conn.execute("INSERT INTO settings_audit (changed_at, key, old_value, new_value, actor) VALUES (?,?,?,?,?)",
                         (_now(), key, str(old), str(value), actor))

    def _fire(self, key: str, value: Any) -> None:
        for fn in self._hooks.get(key, []):
            fn(value)

    def audit(self, limit: int = 100, key: Optional[str] = None) -> list[dict]:
        if not self.db_path:
            return []
        q = "SELECT changed_at, key, old_value, new_value, actor FROM settings_audit"
        args: list = []
        if key:
            q += " WHERE key = ?"
            args.append(key)
        q += " ORDER BY id DESC LIMIT ?"
        args.append(int(limit))
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(q, args).fetchall()]
