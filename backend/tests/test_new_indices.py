import pytest

from app.services import setup_switches
from app.services.strategy_engine import SetupType, INDEX_SYMBOLS
from app.services.strike_selector import (
    get_lot_size, get_strike_step, is_lot_size_known, option_exchange_segment,
)
from app.services.universe_manager import UniverseManager


@pytest.mark.parametrize("sym", ["MIDCPNIFTY", "NIFTYNXT50"])
def test_new_indices_wired(sym):
    inst = UniverseManager().get_instrument(sym)
    assert inst and inst.instrument_type == "INDEX" and inst.exchange_segment == "IDX_I"
    assert sym in INDEX_SYMBOLS
    assert is_lot_size_known(sym)
    assert get_lot_size(sym) > 0
    assert get_strike_step(sym, 10000.0) in (25, 100)
    assert option_exchange_segment(sym) == "NSE_FNO"
    assert setup_switches.block_reason({"1": "index"}, SetupType.SETUP_1_SQUEEZE, sym) is None
    assert setup_switches.block_reason({"1": "stocks"}, SetupType.SETUP_1_SQUEEZE, sym)
