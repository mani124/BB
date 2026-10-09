import pytest
from app.services.universe_manager import UniverseManager
from app.services.strike_selector import get_lot_size

def test_fno_universe_loads_all_stocks():
    mgr = UniverseManager()
    fno_stocks = mgr.get_fno_stocks()
    assert len(fno_stocks) >= 210
    
    # Check key symbols exist
    symbols = [s.symbol for s in fno_stocks]
    assert "TATASTEEL" in symbols
    assert "PAGEIND" in symbols
    assert "360ONE" in symbols
    assert "ABB" in symbols
    assert "RELIANCE" in symbols

    # Check properties
    assert all(s.instrument_type == "EQUITY" for s in fno_stocks)
    assert all(s.exchange_segment == "NSE_EQ" for s in fno_stocks)
    assert all(s.default_timeframe == "5m" for s in fno_stocks)
    assert all(len(s.security_id) > 0 for s in fno_stocks)

def test_fno_universe_instrument_lookup():
    mgr = UniverseManager()
    inst = mgr.get_instrument("PAGEIND")
    assert inst is not None
    assert inst.symbol == "PAGEIND"
    assert inst.instrument_type == "EQUITY"

    idx_inst = mgr.get_instrument("NIFTY 50")
    assert idx_inst is not None
    assert idx_inst.instrument_type == "INDEX"

def test_strike_selector_resolves_all_fno_lots():
    # Official NSE lot sizes from fno_universe
    assert get_lot_size("PAGEIND") == 20
    assert get_lot_size("360ONE") == 500
    assert get_lot_size("TATASTEEL") == 2750
    assert get_lot_size("RELIANCE") == 500
    assert get_lot_size("NIFTY 50") == 65
