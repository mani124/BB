import pytest
from app.services.strike_selector import recommend_strike, resolve_live_strike_from_chain

def test_snapback_strike_selection_itm_1_pe():
    # Spot 25020. For PE, ATM is 25000 or 25050. 1-ITM strike is 25100 PE.
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25020.0,
        option_type="PE",
        stop_loss=25055.0,
        target_1=24950.0,  # 20-SMA midline
        strike_preference="ITM_1"
    )
    assert rec.recommended_strike >= 25050
    assert "PE" in rec.strike_symbol
    assert rec.option_target_1_pts > 0
    assert rec.option_target_1_price > rec.estimated_option_entry

def test_snapback_strike_selection_itm_1_ce():
    # Spot 24980. For CE, ATM is 25000. 1-ITM strike is 24950 CE.
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
    assert rec.option_target_1_pts > 0
    assert rec.option_target_1_price > rec.estimated_option_entry

def test_resolve_live_strike_from_chain_itm_1():
    mock_oc = {
        "24950.0": {"call_close": 120.0, "put_close": 50.0, "call_security_id": "1001", "put_security_id": "1002"},
        "25000.0": {"call_close": 85.0, "put_close": 80.0, "call_security_id": "1003", "put_security_id": "1004"},
        "25050.0": {"call_close": 55.0, "put_close": 115.0, "call_security_id": "1005", "put_security_id": "1006"},
        "25100.0": {"call_close": 35.0, "put_close": 155.0, "call_security_id": "1007", "put_security_id": "1008"},
    }
    # For PE with spot 25020, 1-ITM is 25050 or 25100 PE
    rec_pe = resolve_live_strike_from_chain(
        symbol="NIFTY 50",
        underlying_price=25020.0,
        option_type="PE",
        option_chain_oc=mock_oc,
        expiry_date="2026-10-15",
        stop_loss=25060.0,
        target_1=24950.0,
        strike_preference="ITM_1"
    )
    assert rec_pe.recommended_strike >= 25050
    assert "PE" in rec_pe.strike_symbol

def test_snapback_strike_selection_atm():
    # Spot 25020. ATM strike is 25000 for NIFTY.
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25020.0,
        option_type="CE",
        stop_loss=24980.0,
        target_1=25080.0,
        strike_preference="ATM"
    )
    assert rec.recommended_strike == 25000
    assert rec.atm_strike == 25000
    assert "CE" in rec.strike_symbol
    assert rec.option_target_1_pts == round(abs(25020.0 - 25080.0) * 0.50, 1)

def test_snapback_target_pts_calculation():
    # Spot 25000, target_1 = 24900 (diff = 100 pts)
    # With ITM_1 delta = 0.54, option_target_1_pts = 54.0 pts
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="PE",
        stop_loss=25050.0,
        target_1=24900.0,
        strike_preference="ITM_1"
    )
    assert rec.option_target_1_pts == 54.0
    assert rec.target_1 == 24900.0

def test_backward_compatibility_omitted_preference():
    rec = recommend_strike("NIFTY 50", 25000.0, "CE", stop_loss=24950.0)
    assert rec.recommended_strike == 24950
    assert rec.target_1 == 25075.0
    assert rec.option_target_1_pts == round(50.0 * 0.55 * 1.5, 1)

def test_strategy_engine_snapback_setups_strike_preference():
    import pandas as pd
    from datetime import datetime, timedelta
    from app.services.indicators import calculate_indicators
    from app.services.strategy_engine import evaluate_signals, SetupType

    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 25000.0
    for i in range(25):
        ts = start_t + timedelta(minutes=5 * i)
        step = 5.0 if i % 2 == 0 else -5.0
        p += step
        records.append({
            "timestamp": ts,
            "open": p - step,
            "high": max(p, p - step) + 10.0,
            "low": min(p, p - step) - 10.0,
            "close": p,
            "volume": 5000
        })
    df = calculate_indicators(pd.DataFrame(records))
    last_idx = len(df) - 1
    df.loc[:, "bandwidth"] = 8.0
    upper_band = df.loc[last_idx, "bb_upper"]
    df.loc[last_idx, "bb_middle"] = 24980.0
    mid_band = df.loc[last_idx, "bb_middle"]

    # Trigger Setup 6 PE pinbar
    df.loc[last_idx, "high"] = upper_band + 20.0
    df.loc[last_idx, "open"] = upper_band - 2.0
    df.loc[last_idx, "close"] = upper_band - 3.0
    df.loc[last_idx, "low"] = upper_band - 4.0
    df.loc[last_idx, "rsi"] = 72.0
    df.loc[last_idx, "adx"] = 20.0

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s6_signals = [s for s in signals if s.setup_type == SetupType.SETUP_6_PINBAR_SNAPBACK and s.option_type == "PE"]
    assert len(s6_signals) >= 1
    sig = s6_signals[0]
    rec = sig.strike_recommendation
    assert rec is not None
    # 1-ITM for PE should be > ATM or ATM + step
    assert rec.recommended_strike >= rec.atm_strike
    # Option target 1 pts must be delta-scaled (delta=0.54) to midline
    expected_pts = round(abs(sig.entry_price - round(mid_band, 2)) * 0.54, 1)
    assert rec.option_target_1_pts == expected_pts

def test_resolve_live_strike_sl_guarantees():
    mock_oc = {}
    rec = resolve_live_strike_from_chain(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="PE",
        option_chain_oc=mock_oc,
        stop_loss=24900.0  # Invalid SL below spot for PE
    )
    assert rec.stop_loss > 25000.0


def test_strategy_engine_setup7_strike_recommendation():
    import pandas as pd
    from datetime import datetime, timedelta
    from app.services.indicators import calculate_indicators
    from app.services.strategy_engine import evaluate_signals, SetupType

    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 25000.0
    for i in range(25):
        ts = start_t + timedelta(minutes=5 * i)
        step = 5.0 if i % 2 == 0 else -5.0
        p += step
        records.append({
            "timestamp": ts,
            "open": p - step,
            "high": max(p, p - step) + 10.0,
            "low": min(p, p - step) - 10.0,
            "close": p,
            "volume": 5000
        })
    df = calculate_indicators(pd.DataFrame(records))
    last_idx = len(df) - 1
    m_idx = last_idx - 2
    in_idx = last_idx - 1
    df.loc[:, "bandwidth"] = 8.0
    df.loc[last_idx, "bb_middle"] = 24980.0
    upper_25 = df.loc[m_idx, "bb_upper_25"]

    # Setup 7 PE: Mother bar t-2 punctures bb_upper_25, bar t-1 is inside bar, bar t is breakdown
    df.loc[m_idx, "high"] = upper_25 + 5.0
    df.loc[m_idx, "low"] = upper_25 - 5.0
    df.loc[m_idx, "close"] = upper_25 + 1.0

    df.loc[in_idx, "high"] = df.loc[m_idx, "high"] - 1.0
    df.loc[in_idx, "low"] = df.loc[m_idx, "low"] + 1.0
    df.loc[in_idx, "close"] = df.loc[in_idx, "high"] - 1.0

    df.loc[last_idx, "high"] = df.loc[in_idx, "low"] + 0.5
    df.loc[last_idx, "low"] = df.loc[in_idx, "low"] - 1.0
    df.loc[last_idx, "close"] = df.loc[in_idx, "low"] - 0.5

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s7_signals = [s for s in signals if s.setup_type == SetupType.SETUP_7_INSIDE_BAR_SNAPBACK and s.option_type == "PE"]
    assert len(s7_signals) >= 1
    sig = s7_signals[0]
    rec = sig.strike_recommendation
    assert rec is not None
    assert "PE" in rec.strike_symbol
    assert rec.recommended_strike >= rec.atm_strike
    assert rec.option_target_1_pts > 0
    assert rec.option_target_1_price > rec.estimated_option_entry


def test_strategy_engine_setup8_strike_recommendation():
    import pandas as pd
    from datetime import datetime, timedelta
    from app.services.indicators import calculate_indicators
    from app.services.strategy_engine import evaluate_signals, SetupType

    records = []
    start_t = datetime(2026, 10, 8, 9, 15)
    p = 25000.0
    for i in range(25):
        ts = start_t + timedelta(minutes=5 * i)
        step = 5.0 if i % 2 == 0 else -5.0
        p += step
        records.append({
            "timestamp": ts,
            "open": p - step,
            "high": max(p, p - step) + 10.0,
            "low": min(p, p - step) - 10.0,
            "close": p,
            "volume": 5000
        })
    df = calculate_indicators(pd.DataFrame(records))
    last_idx = len(df) - 1
    swing1_idx = last_idx - 5
    df.loc[:, "bandwidth"] = 8.0

    # Setup 8 PE: Swing 1 pierced bb_upper with high RSI
    df.loc[swing1_idx, "high"] = df.loc[swing1_idx, "bb_upper"] + 10.0
    df.loc[swing1_idx, "close"] = df.loc[swing1_idx, "bb_upper"] + 5.0
    df.loc[swing1_idx, "rsi"] = 78.0

    # Swing 2 (current bar): retests/exceeds Swing 1 high, but has lower RSI, closes inside band
    df.loc[last_idx, "high"] = df.loc[swing1_idx, "high"] + 2.0
    df.loc[last_idx, "close"] = df.loc[last_idx, "bb_upper"] - 2.0
    df.loc[last_idx, "rsi"] = 70.0

    signals = evaluate_signals("NIFTY 50", df, timeframe="5m")
    s8_signals = [s for s in signals if s.setup_type == SetupType.SETUP_8_DIVERGENCE_SNAPBACK and s.option_type == "PE"]
    assert len(s8_signals) >= 1
    sig = s8_signals[0]
    rec = sig.strike_recommendation
    assert rec is not None
    assert "PE" in rec.strike_symbol
    assert rec.recommended_strike >= rec.atm_strike
    assert rec.option_target_1_pts > 0
    assert rec.option_target_1_price > rec.estimated_option_entry



