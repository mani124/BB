import pytest
from app.services.strike_selector import (
    recommend_strike,
    get_strike_step,
    get_lot_size,
    OptionStrike,
    OptionStrikeRecommendation,
)

def test_option_strike_alias():
    assert OptionStrike is OptionStrikeRecommendation

def test_official_nse_lot_sizes():
    assert get_lot_size("NIFTY 50") == 65
    assert get_lot_size("NIFTY") == 65
    assert get_lot_size("BANKNIFTY") == 30
    assert get_lot_size("NIFTY BANK") == 30
    assert get_lot_size("FINNIFTY") == 65
    assert get_lot_size("NIFTY FINANCIAL SERVICES") == 65
    assert get_lot_size("SENSEX") == 20
    assert get_lot_size("MIDCPNIFTY") == 120
    # Stock lot sizes
    assert get_lot_size("RELIANCE") == 500
    assert get_lot_size("HDFCBANK") == 650
    assert get_lot_size("TCS") == 175
    assert get_lot_size("INFY") == 400
    assert get_lot_size("TATAMOTORS") == 550
    # Whitespace and prefix resilience
    assert get_lot_size("  nifty 50  ") == 65
    assert get_lot_size("NSE:BANKNIFTY") == 30

def test_strike_step_resolution():
    assert get_strike_step("NIFTY 50", 25020) == 50
    assert get_strike_step("NIFTY BANK", 52140) == 100
    assert get_strike_step("FINNIFTY", 24110) == 50
    assert get_strike_step("SENSEX", 82340) == 100
    assert get_strike_step("MIDCPNIFTY", 12500) == 25
    assert get_strike_step("RELIANCE", 2980) == 20
    assert get_strike_step("HDFCBANK", 1680) == 10
    # Price tier fallbacks
    assert get_strike_step("UNKNOWN_PENNY", 150) == 5
    assert get_strike_step("UNKNOWN_MID", 420) == 10
    assert get_strike_step("UNKNOWN_LARGE", 1200) == 20
    assert get_strike_step("UNKNOWN_EXPENSIVE", 4500) == 100

def test_strike_recommendation_ce():
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25035.0,
        option_type="CE",
        stop_loss=24985.0
    )
    assert rec.atm_strike == 25050
    assert rec.recommended_strike == 25000  # 1-strike ITM for CE
    assert rec.strike_symbol == "NIFTY 50 25000 CE"
    assert rec.lot_size == 65
    assert rec.risk == 50.0
    assert rec.stop_loss == 24985.0
    assert rec.target_1 == 25035.0 + 1.5 * 50.0  # 25110.0
    assert rec.target_2 == 25035.0 + 2.5 * 50.0  # 25160.0

def test_strike_recommendation_pe():
    rec = recommend_strike(
        symbol="BANKNIFTY",
        underlying_price=51870.0,
        option_type="PE",
        stop_loss=51970.0
    )
    assert rec.atm_strike == 51900
    assert rec.recommended_strike == 52000  # 1-strike ITM for PE
    assert rec.strike_symbol == "BANKNIFTY 52000 PE"
    assert rec.lot_size == 30
    assert rec.risk == 100.0
    assert rec.stop_loss == 51970.0
    assert rec.target_1 == 51870.0 - 1.5 * 100.0  # 51720.0
    assert rec.target_2 == 51870.0 - 2.5 * 100.0  # 51620.0

def test_mathematical_sl_guarantees_ce():
    # Passed invalid SL above entry
    rec_bad_sl = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="CE",
        stop_loss=25050.0  # Invalid for CE!
    )
    assert rec_bad_sl.stop_loss < 25000.0
    assert rec_bad_sl.risk >= max(50 * 0.25, 2.0)

    # Passed SL with microscopic risk (< min_risk floor)
    rec_micro_risk = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="CE",
        stop_loss=24999.5  # Risk only 0.5 pts
    )
    assert rec_micro_risk.stop_loss < 25000.0
    min_floor = max(50 * 0.25, 2.0)  # 12.5 pts for Nifty
    assert rec_micro_risk.risk >= min_floor
    assert rec_micro_risk.stop_loss == 25000.0 - min_floor

    # Omitted stop_loss (defaults safely)
    rec_default = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="CE"
    )
    assert rec_default.stop_loss < 25000.0
    assert rec_default.risk > 0

def test_mathematical_sl_guarantees_pe():
    # Passed invalid SL below entry
    rec_bad_sl = recommend_strike(
        symbol="BANKNIFTY",
        underlying_price=50000.0,
        option_type="PE",
        stop_loss=49900.0  # Invalid for PE!
    )
    assert rec_bad_sl.stop_loss > 50000.0
    assert rec_bad_sl.risk >= max(100 * 0.25, 2.0)

    # Passed SL with microscopic risk (< min_risk floor)
    rec_micro_risk = recommend_strike(
        symbol="BANKNIFTY",
        underlying_price=50000.0,
        option_type="PE",
        stop_loss=50001.0  # Risk only 1.0 pt
    )
    assert rec_micro_risk.stop_loss > 50000.0
    min_floor = max(100 * 0.25, 2.0)  # 25.0 pts for BankNifty
    assert rec_micro_risk.risk >= min_floor
    assert rec_micro_risk.stop_loss == 50000.0 + min_floor

    # Omitted stop_loss (defaults safely)
    rec_default = recommend_strike(
        symbol="BANKNIFTY",
        underlying_price=50000.0,
        option_type="PE"
    )
    assert rec_default.stop_loss > 50000.0
    assert rec_default.risk > 0

def test_option_premium_levels():
    rec = recommend_strike(
        symbol="NIFTY 50",
        underlying_price=25000.0,
        option_type="CE",
        stop_loss=24950.0  # risk = 50.0
    )
    # Estimated entry must be positive
    assert rec.estimated_option_entry > 0
    # Option SL points capped at 70% of premium
    assert rec.option_sl_pts <= rec.estimated_option_entry * 0.7
    # Option SL price at least 1.0
    assert rec.option_sl_price >= 1.0
    assert rec.option_sl_price == round(rec.estimated_option_entry - rec.option_sl_pts, 1)
    # Option Targets
    assert rec.option_target_1_price == round(rec.estimated_option_entry + rec.option_target_1_pts, 1)
    assert rec.option_target_2_price == round(rec.estimated_option_entry + rec.option_target_2_pts, 1)
    assert rec.option_target_2_price > rec.option_target_1_price > rec.estimated_option_entry

def test_resolve_live_strike_from_chain():
    from app.services.strike_selector import resolve_live_strike_from_chain
    # Mock Dhan option chain for Nifty around 22500
    mock_oc = {
        "22450.000000": {
            "ce": {
                "security_id": 44608,
                "last_price": 160.3,
                "top_ask_price": 160.7,
                "top_bid_price": 160.0,
                "volume": 500000,
                "oi": 1200000,
                "greeks": {"delta": 0.5966, "theta": -12.4, "gamma": 0.0012, "vega": 15.2}
            },
            "pe": {
                "security_id": 44611,
                "last_price": 99.55,
                "top_ask_price": 99.8,
                "top_bid_price": 99.5,
                "volume": 300000,
                "oi": 800000,
                "greeks": {"delta": -0.4112, "theta": -10.1, "gamma": 0.0011, "vega": 14.1}
            }
        },
        "22550.000000": {
            "ce": {
                "security_id": 44614,
                "last_price": 105.5,
                "top_ask_price": 105.6,
                "top_bid_price": 105.4,
                "volume": 200000,
                "oi": 600000,
                "greeks": {"delta": 0.4654}
            },
            "pe": {
                "security_id": 44615,
                "last_price": 144.2,
                "top_ask_price": 144.2,
                "top_bid_price": 144.0,
                "volume": 400000,
                "oi": 950000,
                "greeks": {"delta": -0.5312}
            }
        }
    }

    # At spot 22490, 1-strike ITM for CE is 22450
    rec_ce = resolve_live_strike_from_chain(
        symbol="NIFTY 50",
        underlying_price=22490.0,
        option_type="CE",
        option_chain_oc=mock_oc,
        expiry_date="2026-10-13",
        stop_loss=22450.0
    )
    assert rec_ce.is_live_quote is True
    assert rec_ce.option_security_id == "44608"
    assert rec_ce.recommended_strike == 22450
    assert rec_ce.estimated_option_entry == 160.7  # Enters at top ask price!
    assert rec_ce.real_ask_price == 160.7
    assert rec_ce.real_ltp == 160.3
    assert rec_ce.real_delta == 0.5966
    assert rec_ce.option_sl_price < rec_ce.estimated_option_entry
    assert rec_ce.option_target_1_price > rec_ce.estimated_option_entry

    # At spot 22490, 1-strike ITM for PE is 22550
    rec_pe = resolve_live_strike_from_chain(
        symbol="NIFTY 50",
        underlying_price=22490.0,
        option_type="PE",
        option_chain_oc=mock_oc,
        expiry_date="2026-10-13",
        stop_loss=22530.0
    )
    assert rec_pe.is_live_quote is True
    assert rec_pe.option_security_id == "44615"
    assert rec_pe.recommended_strike == 22550
    assert rec_pe.estimated_option_entry == 144.2
    assert rec_pe.real_delta == 0.5312
