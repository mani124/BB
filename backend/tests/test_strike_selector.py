import pytest
from app.services.strike_selector import recommend_strike, get_strike_step

def test_strike_step_resolution():
    assert get_strike_step("NIFTY 50", 25020) == 50
    assert get_strike_step("NIFTY BANK", 52140) == 100
    assert get_strike_step("FINNIFTY", 24110) == 50
    assert get_strike_step("SENSEX", 82340) == 100
    assert get_strike_step("RELIANCE", 2980) == 20
    assert get_strike_step("HDFCBANK", 1680) == 10

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
    assert rec.risk == 50.0
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
    assert rec.risk == 100.0
    assert rec.target_1 == 51870.0 - 1.5 * 100.0  # 51720.0
    assert rec.target_2 == 51870.0 - 2.5 * 100.0  # 51620.0
