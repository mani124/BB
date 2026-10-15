from typing import Literal, Optional
from pydantic import BaseModel

DEFAULT_LOT_SIZES: dict[str, int] = {
    "NIFTY 50": 65,
    "NIFTY": 65,
    "NIFTY BANK": 30,
    "BANKNIFTY": 30,
    "BANK NIFTY": 30,
    "FINNIFTY": 65,
    "NIFTY FINANCIAL SERVICES": 65,
    "SENSEX": 20,
    "MIDCPNIFTY": 120,
    "RELIANCE": 500,
    "HDFCBANK": 650,
    "ICICIBANK": 700,
    "SBIN": 750,
    "AXISBANK": 625,
    "KOTAKBANK": 400,
    "INFY": 400,
    "TCS": 175,
    "HCLTECH": 350,
    "TECHM": 600,
    "TATAMOTORS": 550,
    "MARUTI": 50,
    "M&M": 350,
    "BAJAJ-AUTO": 75,
    "TATASTEEL": 5500,
    "JSWSTEEL": 675,
    "HINDALCO": 1400,
    "COALINDIA": 2100,
    "ONGC": 3850,
    "LT": 150,
    "ADANIENT": 300,
    "ADANIPORTS": 400,
    "BHARTIARTL": 475,
    "ITC": 1600,
    "TITAN": 175,
    "SUNPHARMA": 350,
    "CIPLA": 650,
    "DRREDDY": 125,
    "BAJFINANCE": 125,
    "BAJAJFINSV": 500,
    "WIPRO": 1500,
    "EICHERMOT": 150,
    "NTPC": 1500,
    "TRENT": 100,
    "BEL": 2700,
}

# Automatically load and enrich lot sizes for all 213 F&O stocks from official master
import json
from pathlib import Path

_FNO_PATH = Path(__file__).resolve().parent.parent / "data" / "fno_universe.json"
if _FNO_PATH.exists():
    try:
        with open(_FNO_PATH, "r") as _f:
            _fno_data = json.load(_f)
            for _sym, _item in _fno_data.items():
                if "lot_size" in _item and _item["lot_size"] > 0:
                    DEFAULT_LOT_SIZES[_sym] = int(_item["lot_size"])
    except Exception:
        pass

def clean_symbol_key(symbol: str) -> str:
    s = symbol.upper().strip()
    for prefix in ("NSE:", "BSE:"):
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    return s

def is_lot_size_known(symbol: str) -> bool:
    return clean_symbol_key(symbol) in DEFAULT_LOT_SIZES


def get_lot_size(symbol: str) -> int:
    clean = clean_symbol_key(symbol)
    return DEFAULT_LOT_SIZES.get(clean, 100)

class OptionStrikeRecommendation(BaseModel):
    symbol: str
    underlying_price: float
    option_type: Literal["CE", "PE"]
    atm_strike: int
    recommended_strike: int  # 1-strike ITM for best delta/gamma balance
    strike_symbol: str
    lot_size: int
    lot_size_known: bool = True  # False => lot size is a guessed default; entries are refused
    # Underlying spot levels
    risk: float
    stop_loss: float
    target_1: float  # 1:1.5 RR
    target_2: float  # 1:2.5 RR
    # Option premium levels (Delta ~ 0.55 or live Greeks)
    estimated_option_entry: float
    option_sl_pts: float
    option_target_1_pts: float
    option_target_2_pts: float
    option_sl_price: float
    option_target_1_price: float
    option_target_2_price: float
    # Live Dhan NSE_FNO resolution fields
    option_security_id: Optional[str] = None
    expiry_date: Optional[str] = None
    real_ask_price: Optional[float] = None
    real_bid_price: Optional[float] = None
    real_ltp: Optional[float] = None
    real_delta: Optional[float] = None
    # Liquidity snapshot from the chain/quote (None when the feed does not carry it).
    real_volume: Optional[float] = None
    real_oi: Optional[float] = None
    real_bid_qty: Optional[float] = None
    real_ask_qty: Optional[float] = None
    # True when the option SL/targets were scaled with a default delta (0.50-0.55) instead of the
    # contract's own Greek, i.e. the premium exits are an approximation.
    delta_assumed: bool = False
    is_live_quote: bool = False
    # Age (seconds) of the chain/tick quote these live fields came from; None = unknown.
    quote_age_s: Optional[float] = None
    quote_as_of: Optional[float] = None  # wall-clock epoch the quote was taken; lets entry re-check age later

# Backwards-compatible alias
OptionStrike = OptionStrikeRecommendation


def _opt_float(value) -> Optional[float]:
    """A feed number as float, or None when it is missing or not numeric."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None

INDEX_STRIKE_STEPS: dict[str, int] = {
    "NIFTY 50": 50,
    "NIFTY": 50,
    "NIFTY BANK": 100,
    "BANKNIFTY": 100,
    "FINNIFTY": 50,
    "NIFTY FINANCIAL SERVICES": 50,
    "SENSEX": 100,
    "MIDCPNIFTY": 25,
}

STOCK_STRIKE_STEPS: dict[str, int] = {
    "RELIANCE": 20,
    "HDFCBANK": 10,
    "ICICIBANK": 10,
    "SBIN": 5,
    "AXISBANK": 10,
    "KOTAKBANK": 10,
    "INFY": 20,
    "TCS": 50,
    "TATAMOTORS": 10,
    "MARUTI": 100,
    "LT": 20,
    "BHARTIARTL": 10,
    "BAJFINANCE": 50,
    "BAJAJFINSV": 20,
    "TATASTEEL": 2,
    "JSWSTEEL": 10,
    "ITC": 5,
    "TITAN": 20,
    "SUNPHARMA": 10,
}

def get_strike_step(symbol: str, price: float) -> int:
    clean_sym = clean_symbol_key(symbol)
    if clean_sym in INDEX_STRIKE_STEPS:
        return INDEX_STRIKE_STEPS[clean_sym]
    if clean_sym in STOCK_STRIKE_STEPS:
        return STOCK_STRIKE_STEPS[clean_sym]
    
    # Generic estimation based on price tier
    if price < 250:
        return 5
    elif price < 500:
        return 10
    elif price < 1500:
        return 20
    elif price < 3500:
        return 50
    else:
        return 100

def estimate_option_entry(symbol: str, underlying_price: float, step: int) -> float:
    """Estimate realistic 1-strike ITM option entry premium based on underlying tier and step."""
    clean = clean_symbol_key(symbol)
    # Exact index names only: a substring test made AUBANK, BANKBARODA, YESBANK, ... "indices".
    is_index = clean in INDEX_STRIKE_STEPS
    if is_index:
        # Intrinsic step value + ~0.5% extrinsic time value
        return round(float(step) + (underlying_price * 0.005), 1)
    else:
        # Stock options: step intrinsic + ~1.5% time value
        return round(max(5.0, float(step) + (underlying_price * 0.015)), 1)

def recommend_strike(
    symbol: str,
    underlying_price: float,
    option_type: Literal["CE", "PE"],
    stop_loss: Optional[float] = None,
    target_1: Optional[float] = None,
    target_2: Optional[float] = None,
    strike_preference: str = "DEFAULT",
) -> OptionStrikeRecommendation:
    step = get_strike_step(symbol, underlying_price)
    lot_size = get_lot_size(symbol)
    min_risk = max(step * 0.25, 2.0)
    
    # ATM strike
    atm_strike = int(round(underlying_price / step) * step)

    pref = (strike_preference or "DEFAULT").upper()
    if pref == "ATM":
        recommended_strike = atm_strike
        delta = 0.50
    elif pref == "ITM_1":
        if option_type == "CE":
            recommended_strike = atm_strike - step
        else:
            recommended_strike = atm_strike + step
        delta = 0.54
    else:  # "DEFAULT"
        if option_type == "CE":
            recommended_strike = atm_strike - step
        else:
            recommended_strike = atm_strike + step
        delta = 0.55
    
    # Mathematical SL guarantees
    if option_type == "CE":
        # Mathematical guarantee: SL must strictly be < entry for CE
        if stop_loss is None or stop_loss >= underlying_price:
            stop_loss = underlying_price - max(step * 0.5, min_risk)
        risk = underlying_price - stop_loss
        if risk < min_risk:
            risk = min_risk
            stop_loss = underlying_price - risk
    else:
        # Mathematical guarantee: SL must strictly be > entry for PE
        if stop_loss is None or stop_loss <= underlying_price:
            stop_loss = underlying_price + max(step * 0.5, min_risk)
        risk = stop_loss - underlying_price
        if risk < min_risk:
            risk = min_risk
            stop_loss = underlying_price + risk

    risk = round(risk, 2)
    stop_loss = round(stop_loss, 2)
    strike_symbol = f"{symbol} {recommended_strike} {option_type}"
    
    # Dual Risk/Reward target calculations on underlying price
    if target_1 is not None:
        calc_target_1 = float(target_1)
    else:
        calc_target_1 = round(underlying_price + 1.5 * risk, 2) if option_type == "CE" else round(underlying_price - 1.5 * risk, 2)

    if target_2 is not None:
        calc_target_2 = float(target_2)
    else:
        calc_target_2 = round(underlying_price + 2.5 * risk, 2) if option_type == "CE" else round(underlying_price - 2.5 * risk, 2)

    est_entry = estimate_option_entry(symbol, underlying_price, step)
    # Cap option points risk at max 70% of premium
    opt_sl_pts = round(min(risk * delta, est_entry * 0.7), 1)

    if target_1 is not None:
        opt_t1_pts = round(abs(underlying_price - target_1) * delta, 1)
    else:
        opt_t1_pts = round(risk * delta * 1.5, 1)

    if target_2 is not None:
        opt_t2_pts = round(abs(underlying_price - target_2) * delta, 1)
    else:
        opt_t2_pts = round(risk * delta * 2.5, 1)
    
    opt_sl_price = round(max(1.0, est_entry - opt_sl_pts), 1)
    opt_t1_price = round(est_entry + opt_t1_pts, 1)
    opt_t2_price = round(est_entry + opt_t2_pts, 1)

    return OptionStrikeRecommendation(
        symbol=symbol,
        underlying_price=round(underlying_price, 2),
        option_type=option_type,
        atm_strike=atm_strike,
        recommended_strike=recommended_strike,
        strike_symbol=strike_symbol,
        lot_size=lot_size,
        lot_size_known=is_lot_size_known(symbol),
        risk=risk,
        stop_loss=stop_loss,
        target_1=round(calc_target_1, 2),
        target_2=round(calc_target_2, 2),
        estimated_option_entry=est_entry,
        option_sl_pts=opt_sl_pts,
        option_target_1_pts=opt_t1_pts,
        option_target_2_pts=opt_t2_pts,
        option_sl_price=opt_sl_price,
        option_target_1_price=opt_t1_price,
        option_target_2_price=opt_t2_price
    )


def chain_strike_grid(option_chain_oc: dict) -> list[float]:
    out: list[float] = []
    for k in (option_chain_oc or {}).keys():
        try:
            out.append(float(k))
        except (ValueError, TypeError):
            continue
    return sorted(set(out))


def _chain_step(strikes: list[float]) -> float:
    gaps = sorted(b - a for a, b in zip(strikes, strikes[1:]) if b - a > 0)
    return gaps[len(gaps) // 2] if gaps else 1.0


def _num(v: float):
    return int(v) if float(v).is_integer() else v


def resolve_live_strike_from_chain(
    symbol: str,
    underlying_price: float,
    option_type: Literal["CE", "PE"],
    option_chain_oc: dict,
    expiry_date: str = "",
    stop_loss: Optional[float] = None,
    target_1: Optional[float] = None,
    target_2: Optional[float] = None,
    strike_preference: str = "DEFAULT",
) -> OptionStrikeRecommendation:
    """
    Given a live Dhan option chain 'oc' dictionary, find the exact strike contract based on preference,
    extract its real market quotes (Ask/LTP, Greeks), and calculate mathematically sound
    Option SL and Target levels based on real entry price and real Delta.
    """
    lot_size = get_lot_size(symbol)

    # P2-6: take the strike grid from the live chain itself (nearest listed strike, real step);
    # fall back to the static table only when the chain has too few strikes to infer a grid.
    chain_strikes = chain_strike_grid(option_chain_oc)
    if len(chain_strikes) >= 3 and all(float(k).is_integer() for k in chain_strikes):
        step = _chain_step(chain_strikes)
        atm_idx = min(range(len(chain_strikes)), key=lambda j: abs(chain_strikes[j] - underlying_price))
        atm_strike = _num(chain_strikes[atm_idx])
        pref_u = (strike_preference or "DEFAULT").upper()
        shift = 0 if pref_u == "ATM" else (-1 if option_type == "CE" else 1)
        rec_idx = max(0, min(len(chain_strikes) - 1, atm_idx + shift))
        recommended_strike = _num(chain_strikes[rec_idx])
        default_delta = {"ATM": 0.50, "ITM_1": 0.54}.get(pref_u, 0.55)
    else:
        step = get_strike_step(symbol, underlying_price)
        atm_strike = int(round(underlying_price / step) * step)
        pref = (strike_preference or "DEFAULT").upper()
        if pref == "ATM":
            recommended_strike = atm_strike
            default_delta = 0.50
        else:
            recommended_strike = atm_strike - step if option_type == "CE" else atm_strike + step
            default_delta = 0.54 if pref == "ITM_1" else 0.55
    min_risk = max(step * 0.25, 2.0)

    if option_type == "CE":
        if stop_loss is None or stop_loss >= underlying_price:
            stop_loss = underlying_price - max(step * 0.5, min_risk)
        risk = underlying_price - stop_loss
        if risk < min_risk:
            risk = min_risk
            stop_loss = underlying_price - risk
    else:
        if stop_loss is None or stop_loss <= underlying_price:
            stop_loss = underlying_price + max(step * 0.5, min_risk)
        risk = stop_loss - underlying_price
        if risk < min_risk:
            risk = min_risk
            stop_loss = underlying_price + risk

    risk = round(risk, 2)
    stop_loss = round(stop_loss, 2)
    strike_symbol = f"{symbol} {recommended_strike} {option_type}"

    # Spot targets
    if target_1 is not None:
        calc_target_1 = float(target_1)
    else:
        calc_target_1 = round(underlying_price + 1.5 * risk, 2) if option_type == "CE" else round(underlying_price - 1.5 * risk, 2)

    if target_2 is not None:
        calc_target_2 = float(target_2)
    else:
        calc_target_2 = round(underlying_price + 2.5 * risk, 2) if option_type == "CE" else round(underlying_price - 2.5 * risk, 2)

    # Search in oc for matching strike
    target_f = float(recommended_strike)
    matched_data = None
    for k, v in option_chain_oc.items():
        try:
            if abs(float(k) - target_f) < 0.5:
                matched_data = v
                break
        except (ValueError, TypeError):
            continue

    opt_contract = None
    if matched_data and isinstance(matched_data, dict):
        opt_contract = matched_data.get(option_type.lower())
        if not opt_contract:
            # Handle alternative flat format e.g. call_close / put_close
            close_key = "call_close" if option_type == "CE" else "put_close"
            sec_key = "call_security_id" if option_type == "CE" else "put_security_id"
            if close_key in matched_data:
                price_val = float(matched_data.get(close_key, 0.0))
                opt_contract = {
                    "security_id": matched_data.get(sec_key, ""),
                    "last_price": price_val,
                    "top_ask_price": price_val,
                    "top_bid_price": price_val,
                    "greeks": {"delta": default_delta},
                    "delta_assumed": True,
                }

    if opt_contract and isinstance(opt_contract, dict):
        sec_id = str(opt_contract.get("security_id", ""))
        ltp = float(opt_contract.get("last_price", 0.0))
        ask = float(opt_contract.get("top_ask_price", 0.0))
        bid = float(opt_contract.get("top_bid_price", 0.0))
        greeks = opt_contract.get("greeks") or {}
        raw_delta = float(greeks.get("delta", 0.0))
        delta_assumed = bool(opt_contract.get("delta_assumed")) or not (0.05 <= abs(raw_delta) <= 0.95)
        delta = abs(raw_delta) if (0.05 <= abs(raw_delta) <= 0.95) else default_delta

        # For buying an option: entry is the real Ask price (or LTP if Ask is 0)
        entry_price = ask if ask > 0 else (ltp if ltp > 0 else estimate_option_entry(symbol, underlying_price, step))
        entry_price = round(entry_price, 2)

        opt_sl_pts = round(min(risk * delta, entry_price * 0.7), 1)

        if target_1 is not None:
            opt_t1_pts = round(abs(underlying_price - target_1) * delta, 1)
        else:
            opt_t1_pts = round(risk * delta * 1.5, 1)

        if target_2 is not None:
            opt_t2_pts = round(abs(underlying_price - target_2) * delta, 1)
        else:
            opt_t2_pts = round(risk * delta * 2.5, 1)

        opt_sl_price = round(max(0.5, entry_price - opt_sl_pts), 1)
        opt_t1_price = round(entry_price + opt_t1_pts, 1)
        opt_t2_price = round(entry_price + opt_t2_pts, 1)

        return OptionStrikeRecommendation(
            symbol=symbol,
            underlying_price=round(underlying_price, 2),
            option_type=option_type,
            atm_strike=atm_strike,
            recommended_strike=recommended_strike,
            strike_symbol=strike_symbol,
            lot_size=lot_size,
        lot_size_known=is_lot_size_known(symbol),
            risk=risk,
            stop_loss=stop_loss,
            target_1=round(calc_target_1, 2),
            target_2=round(calc_target_2, 2),
            estimated_option_entry=entry_price,
            option_sl_pts=opt_sl_pts,
            option_target_1_pts=opt_t1_pts,
            option_target_2_pts=opt_t2_pts,
            option_sl_price=opt_sl_price,
            option_target_1_price=opt_t1_price,
            option_target_2_price=opt_t2_price,
            option_security_id=sec_id,
            expiry_date=expiry_date,
            real_ask_price=ask,
            real_bid_price=bid,
            real_volume=_opt_float(opt_contract.get("volume")),
            real_oi=_opt_float(opt_contract.get("oi")),
            real_bid_qty=_opt_float(opt_contract.get("top_bid_quantity")),
            real_ask_qty=_opt_float(opt_contract.get("top_ask_quantity")),
            real_ltp=ltp,
            real_delta=round(delta, 4),
            delta_assumed=delta_assumed,
            is_live_quote=(ask > 0 or ltp > 0),
        )

    # Fallback if strike not resolved from chain
    rec = recommend_strike(
        symbol=symbol,
        underlying_price=underlying_price,
        option_type=option_type,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        strike_preference=strike_preference
    )
    rec.expiry_date = expiry_date
    return rec
