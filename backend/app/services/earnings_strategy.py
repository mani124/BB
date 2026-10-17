"""Stock earnings options: the decision rules, as pure functions (no I/O, no clock, no global state).

Two modes, both parameterised by runtime settings (nothing is hardcoded here):

* Mode A "pre-earnings run-up": buy an ATM straddle ``far_days`` to ``near_days`` calendar days before the
  announcement and sell it before the market can react to the result. Stop on a percentage loss of the premium.
* Mode B "post-earnings IV crush": sell a defined-risk iron condor at the close before the market reacts, buy it
  back after the open on the reaction day, once implied volatility has collapsed.

Timing follows the announcement ``session``: BMO (before market open) means the market reacts that same day, AMC
(after market close) means it reacts on the next trading day. The last safe close is the trading day before the
reaction day. Weekend announcements react on Monday.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from app.services import market_hours

MODE_A = "MODE_A_RUNUP"
MODE_B = "MODE_B_CRUSH"
SESSIONS = ("BMO", "AMC")


# ------------------------------------------------------------------ calendar maths
def prev_trading_day(d: date, n: int = 1) -> date:
    """The n-th trading day strictly before `d`."""
    cur = d
    for _ in range(max(0, n)):
        cur -= timedelta(days=1)
        for _guard in range(15):
            if market_hours.is_trading_day(cur):
                break
            cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    cur = d + timedelta(days=1)
    for _guard in range(15):
        if market_hours.is_trading_day(cur):
            return cur
        cur += timedelta(days=1)
    return cur


def resolve_session(row_session: Optional[str], default_policy: str) -> Optional[str]:
    """BMO / AMC for the row, else the default policy; None when the row cannot be traded (SKIP)."""
    s = (row_session or "").strip().upper()
    if s in SESSIONS:
        return s
    d = (default_policy or "").strip().upper()
    return d if d in SESSIONS else None


def reaction_day(earnings_date: date, session: str) -> date:
    """First trading session in which the market can react to the result."""
    if session == "AMC" or not market_hours.is_trading_day(earnings_date):
        return next_trading_day(earnings_date)
    return earnings_date


def last_safe_close(earnings_date: date, session: str) -> date:
    """Last trading day whose close happens before the result can move the stock."""
    return prev_trading_day(reaction_day(earnings_date, session))


def mode_a_exit_date(earnings_date: date, session: str, exit_days_before: int) -> date:
    day = last_safe_close(earnings_date, session)
    return prev_trading_day(day, exit_days_before - 1) if exit_days_before > 1 else day


def mode_a_in_window(today: date, earnings_date: date, far_days: int, near_days: int) -> bool:
    lo, hi = min(near_days, far_days), max(near_days, far_days)
    return lo <= (earnings_date - today).days <= hi


def mode_b_entry_date(earnings_date: date, session: str) -> date:
    return last_safe_close(earnings_date, session)


def mode_b_exit_date(earnings_date: date, session: str) -> date:
    return reaction_day(earnings_date, session)


def choose_expiry(expiries: list[date], needed_until: date, min_days: int) -> Optional[date]:
    """Earliest listed expiry that is at least `min_days` after the date the position must be closed by.

    This is what keeps the trade clear of the physical-settlement window: if the nearest expiry is too close,
    contract selection rolls to the next one automatically."""
    for e in sorted(expiries):
        if (e - needed_until).days >= min_days:
            return e
    return None


# ------------------------------------------------------------------ chain helpers
def _f(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (TypeError, ValueError):
        return 0.0


def strike_grid(oc: dict) -> list[float]:
    out = []
    for k in (oc or {}):
        try:
            out.append(float(k))
        except (TypeError, ValueError):
            continue
    return sorted(set(out))


def contract(oc: dict, strike: float, opt: str) -> Optional[dict]:
    """The chain entry for a strike/side, normalised to the fields the strategy uses, or None."""
    for k, v in (oc or {}).items():
        try:
            if abs(float(k) - strike) < 0.5 and isinstance(v, dict):
                c = v.get(opt.lower())
                if not isinstance(c, dict):
                    return None
                return {
                    "strike": float(strike), "opt": opt.upper(), "security_id": str(c.get("security_id", "")),
                    "ltp": _f(c.get("last_price")), "bid": _f(c.get("top_bid_price")), "ask": _f(c.get("top_ask_price")),
                    "iv": _f(c.get("implied_volatility")), "volume": _f(c.get("volume")), "oi": _f(c.get("oi")),
                    "delta": _f((c.get("greeks") or {}).get("delta")),
                }
        except (TypeError, ValueError):
            continue
    return None


def nearest_strike(grid: list[float], spot: float) -> Optional[float]:
    return min(grid, key=lambda s: abs(s - spot)) if grid else None


def offset_strike(grid: list[float], base: float, steps: int) -> Optional[float]:
    """Strike `steps` grid positions above (positive) or below (negative) `base`, using the chain's real grid."""
    if base not in grid:
        return None
    i = grid.index(base) + steps
    return grid[i] if 0 <= i < len(grid) else None


def buy_price(c: dict) -> float:
    return c["ask"] if c["ask"] > 0 else 0.0  # paying: never assume better than the offer


def sell_price(c: dict) -> float:
    return c["bid"] if c["bid"] > 0 else 0.0  # receiving: never assume better than the bid


def spread_pct(c: dict) -> Optional[float]:
    if c["bid"] > 0 and c["ask"] > 0 and c["ask"] >= c["bid"]:
        mid = (c["ask"] + c["bid"]) / 2
        return (c["ask"] - c["bid"]) / mid * 100 if mid > 0 else None
    return None


def percentile_rank(value: float, history: list[float]) -> Optional[float]:
    """Share of history at or below `value` (IV percentile, 0 to 100)."""
    if not history:
        return None
    return sum(1 for h in history if h <= value) / len(history) * 100.0


def iv_rank(value: float, history: list[float]) -> Optional[float]:
    if not history:
        return None
    lo, hi = min(history), max(history)
    if hi <= lo:
        return None
    return max(0.0, min(100.0, (value - lo) / (hi - lo) * 100.0))


# ------------------------------------------------------------------ results
@dataclass
class Leg:
    security_id: str
    opt: str
    strike: float
    side: str  # "BUY" or "SELL" (the opening side)
    entry_price: float
    bid: float = 0.0
    ask: float = 0.0

    def as_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Candidate:
    mode: str
    symbol: str
    sector: str
    earnings_date: date
    session: str
    expiry: date
    spot: float
    atm: float
    legs: list[Leg]
    lot_size: int
    lots: int
    net_unit: float  # debit paid (A) or credit received (B), per unit
    max_risk: float  # rupees
    exit_date: date
    iv_atm: float = 0.0
    ivp: Optional[float] = None
    ivr: Optional[float] = None
    metrics: dict = field(default_factory=dict)


@dataclass
class Skip:
    code: str
    detail: str = ""
    metrics: dict = field(default_factory=dict)


def _iv_filter(values: dict, history: list[float], min_history: int, policy: str) -> Optional[Skip]:
    """Common IV-history gating. Returns a Skip when the policy says the stock must not trade yet."""
    if len(history) < min_history:
        values["iv_history_days"] = len(history)
        if policy == "skip":
            return Skip("IV_HISTORY_TOO_SHORT", f"{len(history)} of {min_history} days of IV history", values)
    return None


def evaluate_mode_a(*, symbol: str, sector: str, earnings_date: date, session: str, today: date, spot: float,
                    expiries: list[date], oc_for: Any, lot_size: int, lots: int, iv_history: list[float],
                    cfg: dict) -> "Candidate | Skip":
    """Decide whether to buy the straddle. `oc_for(expiry)` returns the chain for an expiry; `cfg` is the runtime settings."""
    if not mode_a_in_window(today, earnings_date, cfg["far_days"], cfg["near_days"]):
        return Skip("OUTSIDE_ENTRY_WINDOW", metrics={"days_to_earnings": (earnings_date - today).days})
    exit_date = mode_a_exit_date(earnings_date, session, cfg["exit_days_before"])
    if exit_date <= today:
        return Skip("EXIT_DATE_NOT_AFTER_ENTRY", metrics={"exit_date": str(exit_date)})
    expiry = choose_expiry(expiries, exit_date, cfg["min_days_to_expiry"])
    if expiry is None:
        return Skip("NO_SAFE_EXPIRY", metrics={"exit_date": str(exit_date), "min_days": cfg["min_days_to_expiry"]})
    oc = oc_for(expiry)
    grid = strike_grid(oc)
    atm = nearest_strike(grid, spot)
    if atm is None:
        return Skip("NO_CHAIN", metrics={"expiry": str(expiry)})
    ce, pe = contract(oc, atm, "CE"), contract(oc, atm, "PE")
    if not ce or not pe or not ce["security_id"] or not pe["security_id"]:
        return Skip("CONTRACT_UNRESOLVED", metrics={"atm": atm})
    pc, pp = buy_price(ce), buy_price(pe)
    if pc <= 0 or pp <= 0:
        return Skip("NO_ASK_QUOTE", metrics={"ce_ask": ce["ask"], "pe_ask": pe["ask"]})
    max_spread = cfg["max_spread_pct"]
    if max_spread > 0:
        for c in (ce, pe):
            sp = spread_pct(c)
            if sp is not None and sp > max_spread:
                return Skip("SPREAD_TOO_WIDE", f"{c['opt']} spread {sp:.1f}%", {"spread_pct": round(sp, 1), "limit": max_spread})
    iv_atm = (ce["iv"] + pe["iv"]) / 2 if ce["iv"] > 0 and pe["iv"] > 0 else max(ce["iv"], pe["iv"])
    metrics = {"atm": atm, "expiry": str(expiry), "iv_atm": round(iv_atm, 2), "spot": spot,
               "days_to_earnings": (earnings_date - today).days, "debit": round(pc + pp, 2)}
    ivp = percentile_rank(iv_atm, iv_history) if len(iv_history) >= cfg["iv_min_history"] and iv_atm > 0 else None
    miss = _iv_filter(metrics, iv_history, cfg["iv_min_history"], cfg["iv_missing_policy"])
    if miss:
        return miss
    if ivp is not None:
        metrics["ivp"] = round(ivp, 1)
        if cfg["max_ivp"] > 0 and ivp > cfg["max_ivp"]:
            return Skip("IV_PERCENTILE_TOO_HIGH", f"IVP {ivp:.0f} above {cfg['max_ivp']:.0f}", metrics)
    elif cfg["max_ivp"] > 0:
        metrics["ivp_unavailable"] = True
    unit = round(pc + pp, 2)
    risk = round(unit * lot_size * lots, 2)
    if cfg["max_capital"] > 0 and risk > cfg["max_capital"]:
        return Skip("CAPITAL_PER_TRADE_EXCEEDED", metrics={**metrics, "premium": risk, "limit": cfg["max_capital"]})
    legs = [Leg(ce["security_id"], "CE", atm, "BUY", pc, ce["bid"], ce["ask"]),
            Leg(pe["security_id"], "PE", atm, "BUY", pp, pe["bid"], pe["ask"])]
    return Candidate(MODE_A, symbol, sector, earnings_date, session, expiry, spot, atm, legs, lot_size, lots, unit, risk,
                     exit_date, iv_atm=iv_atm, ivp=ivp, metrics=metrics)


def evaluate_mode_b(*, symbol: str, sector: str, earnings_date: date, session: str, today: date, spot: float,
                    expiries: list[date], oc_for: Any, lot_size: int, lots: int, iv_history: list[float],
                    cfg: dict) -> "Candidate | Skip":
    entry_day = mode_b_entry_date(earnings_date, session)
    if today != entry_day:
        return Skip("NOT_ENTRY_DAY", metrics={"entry_day": str(entry_day)})
    exit_date = mode_b_exit_date(earnings_date, session)
    expiry = choose_expiry(expiries, exit_date, cfg["min_days_to_expiry"])
    if expiry is None:
        return Skip("NO_SAFE_EXPIRY", metrics={"exit_date": str(exit_date), "min_days": cfg["min_days_to_expiry"]})
    oc = oc_for(expiry)
    grid = strike_grid(oc)
    atm = nearest_strike(grid, spot)
    if atm is None:
        return Skip("NO_CHAIN", metrics={"expiry": str(expiry)})
    s_pe = offset_strike(grid, atm, -cfg["short_steps"])
    s_ce = offset_strike(grid, atm, cfg["short_steps"])
    l_pe = offset_strike(grid, s_pe, -cfg["wing_steps"]) if s_pe is not None else None
    l_ce = offset_strike(grid, s_ce, cfg["wing_steps"]) if s_ce is not None else None
    if None in (s_pe, s_ce, l_pe, l_ce):
        return Skip("STRIKES_OUTSIDE_CHAIN", metrics={"atm": atm, "grid_size": len(grid)})
    spe, lpe = contract(oc, s_pe, "PE"), contract(oc, l_pe, "PE")
    sce, lce = contract(oc, s_ce, "CE"), contract(oc, l_ce, "CE")
    if not all([spe, lpe, sce, lce]) or not all(c["security_id"] for c in (spe, lpe, sce, lce)):
        return Skip("CONTRACT_UNRESOLVED", metrics={"atm": atm})
    p_spe, p_sce = sell_price(spe), sell_price(sce)
    p_lpe, p_lce = buy_price(lpe), buy_price(lce)
    if min(p_spe, p_sce, p_lpe, p_lce) <= 0:
        return Skip("NO_TWO_SIDED_QUOTE", metrics={"atm": atm})
    max_spread = cfg["max_spread_pct"]
    if max_spread > 0:
        for c in (spe, lpe, sce, lce):
            sp = spread_pct(c)
            if sp is not None and sp > max_spread:
                return Skip("SPREAD_TOO_WIDE", f"{c['opt']} {c['strike']:g} spread {sp:.1f}%",
                            {"spread_pct": round(sp, 1), "limit": max_spread})
    credit = round((p_spe - p_lpe) + (p_sce - p_lce), 2)
    width = max(s_pe - l_pe, l_ce - s_ce)
    iv_atm_c = contract(oc, atm, "CE")
    iv_atm_p = contract(oc, atm, "PE")
    ivs = [c["iv"] for c in (iv_atm_c, iv_atm_p) if c and c["iv"] > 0]
    iv_atm = sum(ivs) / len(ivs) if ivs else 0.0
    metrics = {"atm": atm, "expiry": str(expiry), "credit": credit, "width": width, "iv_atm": round(iv_atm, 2), "spot": spot,
               "short_pe": s_pe, "long_pe": l_pe, "short_ce": s_ce, "long_ce": l_ce}
    if credit <= cfg["min_credit"]:
        return Skip("CREDIT_TOO_LOW", f"net credit {credit} <= {cfg['min_credit']}", metrics)
    ivr = iv_rank(iv_atm, iv_history) if len(iv_history) >= cfg["iv_min_history"] and iv_atm > 0 else None
    miss = _iv_filter(metrics, iv_history, cfg["iv_min_history"], cfg["iv_missing_policy"])
    if miss:
        return miss
    if ivr is not None:
        metrics["ivr"] = round(ivr, 1)
        if cfg["min_ivr"] > 0 and ivr < cfg["min_ivr"]:
            return Skip("IV_RANK_TOO_LOW", f"IVR {ivr:.0f} below {cfg['min_ivr']:.0f}", metrics)
    elif cfg["min_ivr"] > 0:
        metrics["ivr_unavailable"] = True
    risk = round((width - credit) * lot_size * lots, 2)
    if risk <= 0:
        return Skip("NON_POSITIVE_RISK", metrics=metrics)
    if cfg["max_capital"] > 0 and risk > cfg["max_capital"]:
        return Skip("CAPITAL_PER_TRADE_EXCEEDED", metrics={**metrics, "max_risk": risk, "limit": cfg["max_capital"]})
    legs = [Leg(lpe["security_id"], "PE", l_pe, "BUY", p_lpe, lpe["bid"], lpe["ask"]),
            Leg(lce["security_id"], "CE", l_ce, "BUY", p_lce, lce["bid"], lce["ask"]),
            Leg(spe["security_id"], "PE", s_pe, "SELL", p_spe, spe["bid"], spe["ask"]),
            Leg(sce["security_id"], "CE", s_ce, "SELL", p_sce, sce["bid"], sce["ask"])]
    return Candidate(MODE_B, symbol, sector, earnings_date, session, expiry, spot, atm, legs, lot_size, lots, credit, risk,
                     exit_date, iv_atm=iv_atm, ivr=ivr, metrics=metrics)


# ------------------------------------------------------------------ valuation and exits
def close_value_per_unit(legs: list[dict]) -> float:
    """Net cash per unit if every leg were closed now at the worse side of the book:
    bought legs are sold at the bid, sold legs are bought back at the ask. Positive = cash in."""
    total = 0.0
    for lg in legs:
        px = _f(lg.get("current_bid" if lg["side"] == "BUY" else "current_ask"))
        if px <= 0:
            px = _f(lg.get("current_ltp")) or _f(lg.get("entry_price"))
        total += px if lg["side"] == "BUY" else -px
    return total


def open_value_per_unit(legs: list[dict]) -> float:
    """Net cash per unit paid (negative) or received (positive) at entry."""
    return sum(-_f(l["entry_price"]) if l["side"] == "BUY" else _f(l["entry_price"]) for l in legs)


def gross_pnl(legs: list[dict], qty: int) -> float:
    return round((open_value_per_unit(legs) + close_value_per_unit(legs)) * qty, 2)


def exit_reason(*, mode: str, today: date, now_minutes: int, exit_date: date, exit_minutes: int, pnl: float,
                premium_paid: float, max_loss_pct: float, spot: float, short_pe: Optional[float],
                short_ce: Optional[float], expiry: date, min_days_to_expiry: int) -> Optional[str]:
    """First rule that says the position must be closed now, or None. Order matters: protective rules first."""
    if mode == MODE_A and max_loss_pct > 0 and premium_paid > 0 and pnl <= -premium_paid * max_loss_pct / 100.0:
        return "STOP_LOSS"
    if mode == MODE_B and short_pe and short_ce and (spot <= short_pe or spot >= short_ce):
        return "SHORT_STRIKE_BREACHED"
    if (expiry - today).days < min_days_to_expiry:
        return "EXPIRY_TOO_CLOSE"
    if today > exit_date or (today == exit_date and now_minutes >= exit_minutes):
        return "SCHEDULED_EXIT"
    return None
