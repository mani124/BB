from datetime import datetime

from scripts.check_mcx_currency_data import nearest_future, summarize_chain


def _row(sym, inst, exch, exp, sid, lot="100"):
    return {"INSTRUMENT": inst, "EXCH_ID": exch, "UNDERLYING_SYMBOL": sym, "SM_EXPIRY_DATE": exp,
            "SECURITY_ID": sid, "LOT_SIZE": lot, "DISPLAY_NAME": f"{sym} {exp}"}


def test_nearest_future_picks_earliest_unexpired():
    rows = [
        _row("CRUDEOIL", "FUTCOM", "MCX", "2026-10-15", "1"),
        _row("CRUDEOIL", "FUTCOM", "MCX", "2026-11-19", "2"),
        _row("CRUDEOIL", "FUTCOM", "MCX", "2026-12-21", "3"),
        _row("CRUDEOIL", "OPTFUT", "MCX", "2026-10-20", "4"),
        _row("GOLDM", "FUTCOM", "MCX", "2026-10-30", "5"),
    ]
    got = nearest_future(rows, "CRUDEOIL", today=datetime(2026, 10, 19))
    assert got["security_id"] == "2" and got["lot_size"] == 100 and got["expiry"] == "2026-11-19"


def test_nearest_future_none_when_absent():
    assert nearest_future([], "USDINR", today=datetime(2026, 10, 19)) is None
    rows = [_row("USDINR", "FUTCUR", "NSE", "2026-09-28", "9")]
    assert nearest_future(rows, "USDINR", today=datetime(2026, 10, 19)) is None


def test_summarize_chain_counts_quality():
    oc = {"100": {"ce": {"last_price": 5, "top_bid_price": 4.9, "top_ask_price": 5.1, "oi": 10, "greeks": {"delta": 0.5}},
                  "pe": {"last_price": 0}}}
    s = summarize_chain(oc)
    assert s == {"strikes": 1, "legs": 2, "with_price": 1, "with_bid_ask": 1, "with_greeks": 1, "with_oi": 1}
