import logging
from typing import Literal, Optional
from datetime import datetime
import pandas as pd
from app.services.strategy_engine import Signal, SetupType
from app.services.strike_selector import OptionStrikeRecommendation

logger = logging.getLogger(__name__)

def evaluate_option_chart_signal(
    symbol: str,
    strike_symbol: str,
    option_type: Literal["CE", "PE"],
    option_df: pd.DataFrame,
    underlying_price: float,
    strike_price: float,
    expiry_date: Optional[str] = None,
    lot_size: int = 50,
    option_security_id: Optional[str] = None,
    timeframe: str = "5m"
) -> Optional[Signal]:
    """
    Setup 5: Standalone Option Chart Bollinger Scalper.
    Applies technical analysis directly to the option premium candle chart:
    1. Premium closes above Option Upper Bollinger Band (Expansion).
    2. Premium strictly above Option Session VWAP (Buyers in control).
    3. Volume Surge: Candle volume >= 1.2x 20-period average (Illiquid filter).
    4. Option RSI >= 58.0.
    """
    required_cols = {"close", "bb_upper", "vwap", "volume", "rsi", "ema_9"}
    if option_df.empty or len(option_df) < 20 or not required_cols.issubset(option_df.columns):
        return None

    last_idx = len(option_df) - 1
    curr = option_df.iloc[last_idx]

    close = float(curr["close"])
    bb_upper = float(curr["bb_upper"])
    vwap = float(curr["vwap"])
    rsi = float(curr["rsi"])
    volume = float(curr["volume"])
    ema_9 = float(curr["ema_9"])

    # 1. Option Upper BB Breakout
    if close <= bb_upper:
        return None

    # 2. Option VWAP Confirmation (Sellers in control if below VWAP)
    if close <= vwap:
        return None

    # 3. Momentum Confirmation (Wilder's RSI >= 58)
    if rsi < 58.0:
        return None

    # 4. Volume Surge Liquidity Filter: Volume must be >= 1.2x 20-bar avg and >= 1000 contracts
    lookback = min(20, len(option_df) - 1)
    if lookback > 0:
        avg_vol = float(option_df["volume"].iloc[last_idx - lookback:last_idx].mean())
    else:
        avg_vol = volume

    if volume < max(1000.0, avg_vol * 1.2):
        return None

    # Dynamic Option Risk and Targets directly on Option Premium points
    bar_range = max(float(curr.get("high", close)) - float(curr.get("low", close)), close * 0.04)
    # Stop loss placed below 9 EMA or breakout bar low, with min 4% buffer
    risk_pts = round(max(close - ema_9, bar_range * 0.5, close * 0.04), 1)
    opt_sl = round(max(0.5, close - risk_pts), 1)
    actual_risk = round(close - opt_sl, 1)

    opt_t1 = round(close + (actual_risk * 1.5), 1)
    opt_t2 = round(close + (actual_risk * 2.5), 1)

    # Underlying spot levels mapped using Delta ~0.55
    spot_risk = round(actual_risk / 0.55, 1)
    spot_entry = round(underlying_price, 2)
    if option_type == "CE":
        spot_sl = round(underlying_price - spot_risk, 2)
        spot_t1 = round(underlying_price + 1.5 * spot_risk, 2)
        spot_t2 = round(underlying_price + 2.5 * spot_risk, 2)
    else:
        spot_sl = round(underlying_price + spot_risk, 2)
        spot_t1 = round(underlying_price - 1.5 * spot_risk, 2)
        spot_t2 = round(underlying_price - 2.5 * spot_risk, 2)

    ts_raw = curr.get("timestamp", last_idx)
    ts_str = str(ts_raw)
    ts_clean = ts_str.replace(":", "").replace("-", "").replace(" ", "_").replace(".", "")
    sig_id = f"{symbol}_{timeframe}_S5_{option_type}_{ts_clean}"

    rec = OptionStrikeRecommendation(
        symbol=symbol,
        underlying_price=spot_entry,
        option_type=option_type,
        atm_strike=int(strike_price),
        recommended_strike=int(strike_price),
        strike_symbol=strike_symbol,
        lot_size=lot_size,
        risk=spot_risk,
        stop_loss=spot_sl,
        target_1=spot_t1,
        target_2=spot_t2,
        estimated_option_entry=close,
        option_sl_pts=actual_risk,
        option_target_1_pts=round(actual_risk * 1.5, 1),
        option_target_2_pts=round(actual_risk * 2.5, 1),
        option_sl_price=opt_sl,
        option_target_1_price=opt_t1,
        option_target_2_price=opt_t2,
        option_security_id=option_security_id,
        expiry_date=expiry_date,
        real_ltp=close,
        is_live_quote=True
    )

    indicators_snap = {
        "option_close": close,
        "option_bb_upper": bb_upper,
        "option_vwap": vwap,
        "option_rsi": rsi,
        "option_volume": volume,
        "option_ema_9": ema_9
    }

    return Signal(
        id=sig_id,
        symbol=symbol,
        timeframe=timeframe,
        setup_type=SetupType.SETUP_5_OPTION_BB,
        option_type=option_type,
        timestamp=ts_str,
        entry_price=spot_entry,
        stop_loss=spot_sl,
        target_1=spot_t1,
        target_2=spot_t2,
        strike_recommendation=rec,
        indicators_snapshot=indicators_snap,
        rationale="Option BB Upper expansion with VWAP & volume surge"
    )
