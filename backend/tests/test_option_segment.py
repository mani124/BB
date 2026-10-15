from app.services.strike_selector import option_exchange_segment


def test_option_segment_per_underlying():
    for sym in ("NIFTY 50", "NIFTY BANK", "FINNIFTY", "RELIANCE", "M&M"):
        assert option_exchange_segment(sym) == "NSE_FNO"
    for sym in ("SENSEX", "BANKEX", "BSE:SENSEX"):
        assert option_exchange_segment(sym) == "BSE_FNO"
