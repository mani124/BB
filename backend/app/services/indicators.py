import numpy as np
import pandas as pd

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute vectorized technical indicators for Bollinger Bands options trading:
    - Bollinger Bands (20, 2.0): Middle, Upper, Lower, BandWidth, BandWidth_20_Min, %B
    - Session VWAP
    - 14-period Wilder's RSI
    - 9-period EMA
    - 14-period ADX
    - 15-Minute Opening Range (09:15-09:30 AM IST)
    """
    if df.empty or len(df) < 5:
        return df

    res = df.copy()
    if not np.issubdtype(res["timestamp"].dtype, np.datetime64):
        res["timestamp"] = pd.to_datetime(res["timestamp"])

    res = res.sort_values("timestamp").reset_index(drop=True)

    # 1. Bollinger Bands (20, 2.0)
    window = min(20, len(res))
    res["bb_middle"] = res["close"].rolling(window=window, min_periods=window).mean()
    res["bb_std"] = res["close"].rolling(window=window, min_periods=window).std(ddof=0)
    res["bb_upper"] = res["bb_middle"] + 2.0 * res["bb_std"]
    res["bb_lower"] = res["bb_middle"] - 2.0 * res["bb_std"]

    # BandWidth = (Upper - Lower) / Middle * 100
    denom = res["bb_middle"].replace(0, np.nan)
    res["bandwidth"] = ((res["bb_upper"] - res["bb_lower"]) / denom * 100.0).fillna(0.0)

    # BandWidth 20-period rolling min (for squeeze detection)
    res["bandwidth_20_min"] = res["bandwidth"].rolling(window=window, min_periods=window).min()

    # Percent B = (Close - Lower) / (Upper - Lower)
    band_diff = (res["bb_upper"] - res["bb_lower"]).replace(0, np.nan)
    res["percent_b"] = ((res["close"] - res["bb_lower"]) / band_diff).fillna(0.5)

    # 2. Session VWAP
    # Typical price = (H + L + C) / 3
    typical_price = (res["high"] + res["low"] + res["close"]) / 3.0
    res["session_date"] = res["timestamp"].dt.date
    
    tp_vol = typical_price * res["volume"]
    cum_tp_vol = tp_vol.groupby(res["session_date"]).cumsum()
    cum_vol = res["volume"].groupby(res["session_date"]).cumsum()
    
    res["vwap"] = (cum_tp_vol / cum_vol.replace(0, np.nan)).fillna(typical_price)
    res.drop(columns=["session_date"], inplace=True)

    # 3. 14-period Wilder's RSI
    delta = res["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    res["rsi"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

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
    plus_di14 = (pd.Series(plus_dm).ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean() / atr14.replace(0, np.nan)) * 100.0
    minus_di14 = (pd.Series(minus_dm).ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean() / atr14.replace(0, np.nan)) * 100.0

    dx = ((plus_di14 - minus_di14).abs() / (plus_di14 + minus_di14).replace(0, np.nan)) * 100.0
    res["adx"] = dx.ewm(alpha=1.0 / 14.0, min_periods=14, adjust=False).mean().fillna(20.0)

    # 6. Opening Range (09:15 - 09:30 AM IST)
    # Filter bars starting between 09:15 and 09:29:59
    time_series = res["timestamp"].dt.time
    t_start = pd.to_datetime("09:15:00").time()
    t_end = pd.to_datetime("09:30:00").time()
    
    or_mask = (time_series >= t_start) & (time_series < t_end)
    or_high_val = res.loc[or_mask, "high"].max() if or_mask.any() else res["high"].iloc[:3].max()
    or_low_val = res.loc[or_mask, "low"].min() if or_mask.any() else res["low"].iloc[:3].min()

    res["or_high"] = or_high_val
    res["or_low"] = or_low_val

    return res
