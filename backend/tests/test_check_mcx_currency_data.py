from datetime import datetime

from scripts.check_mcx_currency_data import diagnose_missing, future_expiry_summary, nearest_futures, option_expiry_summary, option_underlyings, parity_atm, probe_contracts, summarize_chain


def _row(sym, inst, exch, exp, sid, lot="100"):
    return {"INSTRUMENT": inst, "EXCH_ID": exch, "UNDERLYING_SYMBOL": sym, "SM_EXPIRY_DATE": exp,
            "SECURITY_ID": sid, "LOT_SIZE": lot, "DISPLAY_NAME": f"{sym} {exp}"}


def test_nearest_futures_rolls_past_today_and_skips_the_mini():
    rows = [
        _row("CRUDEOIL", "FUTCOM", "MCX", "2026-10-19", "1"),
        _row("CRUDEOIL", "FUTCOM", "MCX", "2026-11-19", "2"),
        _row("CRUDEOIL", "FUTCOM", "MCX", "2026-12-21", "3"),
        _row("CRUDEOILM", "FUTCOM", "MCX", "2026-11-19", "6"),
        _row("CRUDEOIL", "OPTFUT", "MCX", "2026-10-20", "4"),
    ]
    got = nearest_futures(rows, "CRUDEOIL", today=datetime(2026, 10, 19))
    assert [g["security_id"] for g in got] == ["2", "3"]


def test_currency_matching_is_lenient_and_diagnosis_explains_a_miss():
    row = {"INSTRUMENT": "FUTCUR", "EXCH_ID": "NSE", "SM_EXPIRY_DATE": "2026-10-28", "SECURITY_ID": "9", "LOT_SIZE": "1",
           "UNDERLYING_SYMBOL": "", "SYMBOL_NAME": "USDINR"}
    assert nearest_futures([row], "USDINR", today=datetime(2026, 10, 19))[0]["security_id"] == "9"
    assert nearest_futures([], "USDINR", today=datetime(2026, 10, 19)) == []
    assert any("none" in line for line in diagnose_missing([], "USDINR"))


def test_parity_atm_picks_the_strike_where_call_and_put_match():
    oc = {"100": {"ce": {"last_price": 9}, "pe": {"last_price": 1}}, "110": {"ce": {"last_price": 5}, "pe": {"last_price": 5.2}}}
    assert parity_atm(oc) == 110.0


def test_summarize_chain_counts_quality():
    oc = {"100": {"ce": {"last_price": 5, "top_bid_price": 4.9, "top_ask_price": 5.1, "oi": 10, "greeks": {"delta": 0.5}},
                  "pe": {"last_price": 0}}}
    s = summarize_chain(oc)
    assert s == {"strikes": 1, "legs": 2, "with_price": 1, "with_bid_ask": 1, "with_greeks": 1, "with_oi": 1}


def test_option_underlying_fallback_and_stale_future_summary():
    rows = [_row("USDINR", "FUTCUR", "NSE", "2024-08-28", "1"),
            {**_row("USDINR", "OPTCUR", "NSE", "2026-10-28", "5"), "UNDERLYING_SECURITY_ID": "20001.0"}]
    assert nearest_futures(rows, "USDINR", today=datetime(2026, 10, 19)) == []
    assert option_underlyings(rows, "USDINR", today=datetime(2026, 10, 19))[0]["security_id"] == "20001"
    assert "2024-08-28" in future_expiry_summary(rows, "USDINR")


def test_stale_master_is_probed_instead_of_ending_the_run():
    rows = [_row("USDINR", "FUTCUR", "NSE", "2026-06-26", "11"),
            {**_row("USDINR", "OPTCUR", "NSE", "2026-06-26", "5"), "UNDERLYING_SECURITY_ID": "20001.0"},
            {**_row("USDINR", "OPTCUR", "NSE", "2026-05-27", "6"), "UNDERLYING_SECURITY_ID": "20000"}]
    today = datetime(2026, 10, 19)
    assert nearest_futures(rows, "USDINR", today=today) == [] and option_underlyings(rows, "USDINR", today=today) == []
    ids = [c["security_id"] for c in probe_contracts(rows, "USDINR")]
    assert ids == ["20001", "20000", "11"]
    assert "2 expiries" in option_expiry_summary(rows, "USDINR")
