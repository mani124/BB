import pytest
import pandas as pd
from datetime import datetime, timedelta
from app.services.indicators import calculate_indicators
from app.services.strategy_engine import SetupType
from app.services.option_chart_strategy import evaluate_option_chart_signal

from typing import Optional

def create_option_candles(
    n: int = 30,
    base_premium: float = 120.0,
    start_time: Optional[datetime] = None
) -> pd.DataFrame:
    """Create a realistic sequence of option premium candles."""
    if start_time is None:
        start_time = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(hours=3)
    records = []
    prem = base_premium
    for i in range(n):
        ts = start_time + timedelta(minutes=5 * i)
        # Low volatility oscillation
        step = 0.5 if i % 2 == 0 else -0.5
        prem += step
        records.append({
            "timestamp": ts,
            "open": round(prem - 0.2, 2),
            "high": round(prem + 0.8, 2),
            "low": round(prem - 0.8, 2),
            "close": round(prem, 2),
            "volume": 10000
        })
    return pd.DataFrame(records)

def test_setup5_ce_breakout_above_option_upper_bb_and_vwap():
    df = create_option_candles(n=30, base_premium=100.0)
    # Candle 30: strong surge breaking above option Upper BB with high volume
    ts = datetime.now()
    df.loc[29] = {
        "timestamp": ts,
        "open": 101.0,
        "high": 115.0,
        "low": 100.5,
        "close": 114.0,  # massive expansion above BB
        "volume": 45000  # 4.5x surge volume
    }

    ind_df = calculate_indicators(df)
    signal = evaluate_option_chart_signal(
        symbol="RELIANCE",
        strike_symbol="RELIANCE 3000 CE",
        option_type="CE",
        option_df=ind_df,
        underlying_price=2985.0,
        strike_price=3000.0,
        expiry_date="2026-10-29",
        lot_size=500,
        option_security_id="54321"
    )

    assert signal is not None, "Setup 5 CE signal should trigger on option BB breakout with volume"
    assert signal.setup_type == SetupType.SETUP_5_OPTION_BB
    assert signal.option_type == "CE"
    assert signal.symbol == "RELIANCE"
    assert signal.entry_price == 114.0
    assert signal.stop_loss < 114.0
    assert signal.target_1 > 114.0
    assert signal.target_2 > signal.target_1
    assert signal.strike_recommendation.estimated_option_entry == 114.0
    assert signal.strike_recommendation.option_sl_price < 114.0
    assert signal.strike_recommendation.option_target_1_price > 114.0
    assert signal.strike_recommendation.strike_symbol == "RELIANCE 3000 CE"
    assert signal.strike_recommendation.option_security_id == "54321"
    assert "Option BB Upper expansion with VWAP & volume surge" in signal.rationale

def test_setup5_ce_rejected_when_below_option_vwap():
    df = create_option_candles(n=30, base_premium=100.0)
    # Candle 30: closes high relative to bar, but earlier bars had high price/volume pulling VWAP higher
    # Artificially override vwap to be above close
    ind_df = calculate_indicators(df)
    # Force option close below option vwap
    ind_df.loc[29, "close"] = 110.0
    ind_df.loc[29, "bb_upper"] = 108.0
    ind_df.loc[29, "vwap"] = 115.0  # VWAP higher than price (sellers in control)
    ind_df.loc[29, "volume"] = 30000
    ind_df.loc[29, "rsi"] = 62.0

    signal = evaluate_option_chart_signal(
        symbol="RELIANCE",
        strike_symbol="RELIANCE 3000 CE",
        option_type="CE",
        option_df=ind_df,
        underlying_price=2985.0,
        strike_price=3000.0,
        expiry_date="2026-10-29",
        lot_size=500,
        option_security_id="54321"
    )

    assert signal is None, "Setup 5 must reject when option premium is below Option VWAP"

def test_setup5_ce_rejected_when_low_volume():
    df = create_option_candles(n=30, base_premium=100.0)
    ind_df = calculate_indicators(df)
    # Close above BB upper and above VWAP, but tiny volume (illiquid tick)
    ind_df.loc[29, "close"] = 112.0
    ind_df.loc[29, "bb_upper"] = 108.0
    ind_df.loc[29, "vwap"] = 105.0
    ind_df.loc[29, "volume"] = 500  # far below 10,000 avg
    ind_df.loc[29, "rsi"] = 65.0

    signal = evaluate_option_chart_signal(
        symbol="RELIANCE",
        strike_symbol="RELIANCE 3000 CE",
        option_type="CE",
        option_df=ind_df,
        underlying_price=2985.0,
        strike_price=3000.0,
        expiry_date="2026-10-29",
        lot_size=500,
        option_security_id="54321"
    )

    assert signal is None, "Setup 5 must reject when volume surge is missing (illiquid option protection)"

def test_setup5_pe_breakout_above_option_upper_bb_and_vwap():
    df = create_option_candles(n=30, base_premium=80.0)
    ts = datetime.now()
    df.loc[29] = {
        "timestamp": ts,
        "open": 82.0,
        "high": 96.0,
        "low": 81.0,
        "close": 95.0,  # Put premium expands upward as stock crashes
        "volume": 35000
    }

    ind_df = calculate_indicators(df)
    signal = evaluate_option_chart_signal(
        symbol="NIFTY 50",
        strike_symbol="NIFTY 50 22500 PE",
        option_type="PE",
        option_df=ind_df,
        underlying_price=22480.0,
        strike_price=22500.0,
        expiry_date="2026-10-15",
        lot_size=65,
        option_security_id="44615"
    )

    assert signal is not None, "Setup 5 PE signal should trigger when Put premium expands above its Upper BB"
    assert signal.setup_type == SetupType.SETUP_5_OPTION_BB
    assert signal.option_type == "PE"
    assert signal.entry_price == 95.0
    assert signal.stop_loss < 95.0
    assert signal.target_1 > 95.0
    assert signal.strike_recommendation.estimated_option_entry == 95.0
    assert signal.strike_recommendation.option_sl_price < 95.0
    assert signal.strike_recommendation.option_target_1_price > 95.0

def test_setup5_paper_trader_does_not_instant_exit_on_market_price():
    from app.services.paper_trader import PaperTradingEngine

    df = create_option_candles(n=30, base_premium=100.0)
    df.loc[29] = {
        "timestamp": datetime.now(),
        "open": 101.0,
        "high": 115.0,
        "low": 100.5,
        "close": 114.0,
        "volume": 45000
    }
    ind_df = calculate_indicators(df)
    sig = evaluate_option_chart_signal(
        symbol="RELIANCE",
        strike_symbol="RELIANCE 3000 CE",
        option_type="CE",
        option_df=ind_df,
        underlying_price=2985.0,
        strike_price=3000.0,
        lot_size=500,
        option_security_id="54321"
    )

    engine = PaperTradingEngine()
    engine.set_max_risk_per_trade(15000.0)
    pos = engine.open_position_from_signal(sig, lots=2)
    assert pos is not None
    assert pos.status == "OPEN"
    assert pos.underlying_entry == 114.0
    assert pos.option_entry == 114.0

    # 1. Feeding CURRENT market price (spot 2985.0 and option 114.0) must keep position OPEN
    engine.update_market_prices({"RELIANCE": 2985.0}, {"54321": 114.0})
    portfolio = engine.get_portfolio()
    assert len(portfolio.active_positions) == 1, "Position must remain open on normal market ticks"
    assert len(portfolio.closed_trades) == 0, "No trades should be prematurely closed"
    active = portfolio.active_positions[0]
    assert active.pnl_points == 0.0
    assert active.pnl_rupees == 0.0

    # 2. Even if underlying spot plunges or surges violently, Setup 5 does NOT exit based on spot!
    engine.update_market_prices({"RELIANCE": 2500.0}, {"54321": 114.0})
    assert len(engine.get_portfolio().active_positions) == 1, "Spot plunge must NOT exit Setup 5"

    # 3. Exits are strictly governed by option chart price: simulate option SL hit
    opt_sl = pos.option_sl
    engine.update_market_prices({"RELIANCE": 2985.0}, {"54321": opt_sl - 1.0})
    portfolio = engine.get_portfolio()
    assert len(portfolio.closed_trades) == 1, "Option chart price hitting SL must close position"
    assert portfolio.closed_trades[0].status == "STOPPED_OUT"
    assert portfolio.closed_trades[0].exit_reason == "Stop-Loss Hit"
