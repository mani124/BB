import numpy as np
import pandas as pd

INDICATOR_COLUMNS = [
    "bb_middle",
    "bb_std",
    "bb_upper",
    "bb_lower",
    "bandwidth",
    "bandwidth_20_min",
    "percent_b",
    "vwap",
    "rsi",
    "ema_9",
    "adx",
    "plus_di",
    "minus_di",
    "or_high",
    "or_low",
]


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute vectorized technical indicators for Bollinger Bands options trading:
    - Bollinger Bands (20, 2.0): Middle, Upper, Lower, BandWidth, BandWidth_20_Min, %B
    - Session VWAP (resets per trading session)
    - 14-period Wilder's RSI (with exact zero-loss rally & zero-gain drop bounds)
    - 9-period EMA
    - 14-period ADX (True Range, +DM, -DM, +DI14, -DI14, DX, ADX(14))
    - 15-Minute Opening Range (09:15-09:30 AM IST of the latest trading session)
    """
    if df.empty:
        res = df.copy()
        for col in INDICATOR_COLUMNS:
            if col not in res.columns:
                res[col] = pd.Series(dtype=np.float64)
        return res

    res = df.copy()

    # Normalize timestamp handling (support strings, tz-naive, and tz-aware)
    if not pd.api.types.is_datetime64_any_dtype(res["timestamp"]):
        res["timestamp"] = pd.to_datetime(res["timestamp"])

    # If timezone-aware, convert to Indian Standard Time (IST) for session & ORB alignment
    if res["timestamp"].dt.tz is not None:
        res["timestamp"] = res["timestamp"].dt.tz_convert("Asia/Kolkata")

    res = res.sort_values("timestamp").reset_index(drop=True)

    n_bars = len(res)
    window = min(20, n_bars)

    # 1. Bollinger Bands (20, 2.0)
    res["bb_middle"] = res["close"].rolling(window=window, min_periods=window).mean()
    res["bb_std"] = res["close"].rolling(window=window, min_periods=window).std(ddof=0)
    res["bb_upper"] = res["bb_middle"] + 2.0 * res["bb_std"]
    res["bb_lower"] = res["bb_middle"] - 2.0 * res["bb_std"]

    # BandWidth = (Upper - Lower) / Middle * 100
    denom = res["bb_middle"].replace(0, np.nan)
    raw_bw = (res["bb_upper"] - res["bb_lower"]) / denom * 100.0
    res["bandwidth_20_min"] = (
        raw_bw.rolling(window=window, min_periods=1).min().fillna(0.0)
    )
    res["bandwidth"] = raw_bw.fillna(0.0)

    # Percent B = (Close - Lower) / (Upper - Lower)
    band_diff = (res["bb_upper"] - res["bb_lower"]).replace(0, np.nan)
    res["percent_b"] = ((res["close"] - res["bb_lower"]) / band_diff).fillna(0.5)

    # 2. Session VWAP
    # Typical price = (H + L + C) / 3
    typical_price = (res["high"] + res["low"] + res["close"]) / 3.0
    res["session_date"] = res["timestamp"].dt.date

    vol_clean = res["volume"].fillna(0).clip(lower=0)
    tp_vol = typical_price * vol_clean
    cum_tp_vol = tp_vol.groupby(res["session_date"]).cumsum()
    cum_vol = vol_clean.groupby(res["session_date"]).cumsum()

    res["vwap"] = (cum_tp_vol / cum_vol.replace(0, np.nan)).fillna(typical_price)
    res.drop(columns=["session_date"], inplace=True)

    # 3. 14-period Wilder's RSI
    delta = res["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()

    # Exact Wilder formulation: 100 * AvgGain / (AvgGain + AvgLoss)
    total_change = avg_gain + avg_loss
    with np.errstate(divide="ignore", invalid="ignore"):
        rsi_calc = np.where(total_change == 0, 50.0, (avg_gain / total_change) * 100.0)
    res["rsi"] = pd.Series(rsi_calc, index=res.index).fillna(50.0)

    # 4. 9-period EMA
    res["ema_9"] = res["close"].ewm(span=9, adjust=False).mean()

    # 5. 14-period ADX (Average Directional Index)
    prev_close = res["close"].shift(1)
    tr1 = res["high"] - res["low"]
    tr2 = (res["high"] - prev_close).abs()
    tr3 = (res["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    up_move = res["high"] - res["high"].shift(1)
    down_move = res["low"].shift(1) - res["low"]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr14 = tr.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    atr14_safe = atr14.replace(0, np.nan)
    plus_di14 = (
        pd.Series(plus_dm, index=res.index)
        .ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False)
        .mean()
        / atr14_safe
        * 100.0
    ).fillna(0.0)
    minus_di14 = (
        pd.Series(minus_dm, index=res.index)
        .ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False)
        .mean()
        / atr14_safe
        * 100.0
    ).fillna(0.0)

    res["plus_di"] = plus_di14
    res["minus_di"] = minus_di14

    di_sum = (plus_di14 + minus_di14).replace(0, np.nan)
    di_diff = (plus_di14 - minus_di14).abs()
    dx = (di_diff / di_sum * 100.0).fillna(0.0)
    dx_masked = pd.Series(np.where(atr14.isna(), np.nan, dx), index=res.index)
    res["adx"] = (
        dx_masked.ewm(alpha=1.0 / 14.0, min_periods=1, adjust=False)
        .mean()
        .fillna(20.0)
    )

    # 6. Opening Range (09:15 - 09:30 AM IST of the latest trading session)
    latest_date = res["timestamp"].dt.date.max()
    time_series = res["timestamp"].dt.time
    t_start = pd.to_datetime("09:15:00").time()
    t_end = pd.to_datetime("09:30:00").time()

    or_mask = (
        (res["timestamp"].dt.date == latest_date)
        & (time_series >= t_start)
        & (time_series < t_end)
    )
    fallback_n = min(3, n_bars)
    or_high_val = (
        res.loc[or_mask, "high"].max()
        if or_mask.any()
        else res["high"].iloc[:fallback_n].max()
    )
    or_low_val = (
        res.loc[or_mask, "low"].min()
        if or_mask.any()
        else res["low"].iloc[:fallback_n].min()
    )

    res["or_high"] = float(or_high_val) if pd.notna(or_high_val) else 0.0
    res["or_low"] = float(or_low_val) if pd.notna(or_low_val) else 0.0

    return res
