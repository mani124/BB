"""Compare Setup 1 signal counts for different SQUEEZE_ABS_BW_PCT values on recorded candles.

Usage: python -m scripts.compare_squeeze candles.csv [5.0 3.0 1.5]
CSV columns: timestamp,open,high,low,close,volume  (one symbol, 5m bars, oldest first)
"""
import sys
import pandas as pd
from app.core.config import settings
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import evaluate_signals, SetupType


def count(df: pd.DataFrame, thr: float) -> int:
    settings.SQUEEZE_ABS_BW_PCT = thr
    ind = calculate_indicators(df)
    n = 0
    for i in range(25, len(ind) + 1):
        n += sum(1 for s in evaluate_signals("X", ind.iloc[:i], timeframe="5m")
                 if s.setup_type == SetupType.SETUP_1_SQUEEZE)
    return n


if __name__ == "__main__":
    df = pd.read_csv(sys.argv[1], parse_dates=["timestamp"])
    for t in [float(x) for x in sys.argv[2:]] or [5.0, 3.0, 1.5]:
        print(f"SQUEEZE_ABS_BW_PCT={t}: {count(df, t)} Setup 1 signals")
