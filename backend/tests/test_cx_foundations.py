import asyncio
import json
from datetime import date, datetime

import pytest

from app.services import cx_instruments as ci
from app.services import exchange_sessions as xs
from app.services.charges_calculator import calculate_currency_option_charges, calculate_mcx_option_charges
from app.services.runtime_settings import BY_KEY


def at(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def test_mcx_runs_into_the_evening_but_nse_currency_does_not():
    assert xs.is_session_open(xs.MCX, at("2026-10-19 20:00"))      # Monday evening
    assert not xs.is_session_open(xs.CURRENCY, at("2026-10-19 20:00"))
    assert xs.is_session_open(xs.CURRENCY, at("2026-10-19 16:59"))
    assert not xs.is_session_open(xs.CURRENCY, at("2026-10-19 17:00"))
    assert not xs.is_session_open(xs.MCX, at("2026-10-19 23:30"))


def test_weekend_and_unknown_year_are_closed():
    assert not xs.is_session_open(xs.MCX, at("2026-10-17 12:00"))  # Saturday
    assert not xs.is_session_open(xs.MCX, at("2027-01-05 12:00"))  # no holiday data for 2027: fail closed


def test_nse_holiday_closes_currency_and_mcx_morning_only():
    d = "2026-10-20"  # Dussehra
    assert not xs.is_session_open(xs.CURRENCY, at(f"{d} 11:00"))
    assert not xs.is_session_open(xs.MCX, at(f"{d} 11:00"))
    assert xs.is_session_open(xs.MCX, at(f"{d} 18:00"))
    assert not xs.is_session_open(xs.MCX, at("2026-10-02 18:00"))  # MCX fully closed


def test_entry_cutoff_and_square_off():
    assert xs.is_entry_allowed(xs.MCX, at("2026-10-19 22:29"))
    assert not xs.is_entry_allowed(xs.MCX, at("2026-10-19 22:30"))
    assert not xs.is_square_off_due(xs.MCX, at("2026-10-19 23:14"))
    assert xs.is_square_off_due(xs.MCX, at("2026-10-19 23:15"))
    assert xs.is_square_off_due(xs.CURRENCY, at("2026-10-19 16:50"))
    assert xs.is_square_off_due(xs.CURRENCY, at("2026-10-17 12:00"))  # closed day: nothing is carried


def test_close_time_is_configurable_for_us_dst():
    cfg = xs.SessionConfig(mcx_close="23:55", mcx_square_off="23:40")
    assert xs.is_session_open(xs.MCX, at("2026-10-19 23:40"), cfg)
    assert xs.is_square_off_due(xs.MCX, at("2026-10-19 23:40"), cfg)


def test_config_from_runtime_defaults():
    class R:
        def get(self, k):
            return BY_KEY[k].default
    assert xs.config_from(R()) == xs.SessionConfig()


def test_charges_mcx_has_ctt_and_currency_does_not():
    m = calculate_mcx_option_charges(100.0, 120.0, 100)
    assert m.stt == pytest.approx(120.0 * 100 * 0.0005, abs=0.01)
    assert m.total_charges > m.brokerage
    c = calculate_currency_option_charges(0.5, 0.7, 1000)
    assert c.stt == 0.0 and c.total_charges > c.brokerage
    assert calculate_mcx_option_charges(0, 0, 100).total_charges == 0.0


def _row(sym, inst, exch, exp, sid, lot="100"):
    return {"INSTRUMENT": inst, "EXCH_ID": exch, "UNDERLYING_SYMBOL": sym, "SM_EXPIRY_DATE": exp,
            "SECURITY_ID": sid, "LOT_SIZE": lot}


def test_nearest_futures_and_unknown_lot():
    rows = [_row("USDINR", "FUTCUR", "NSE", "2026-10-28", "1", "1000"), _row("USDINR", "FUTCUR", "NSE", "2026-11-26", "2", "0"),
            _row("USDINR", "FUTCUR", "NSE", "2026-09-28", "0", "1000"), _row("USDINR", "OPTCUR", "NSE", "2026-10-28", "9")]
    got = ci.nearest_futures(rows, "USDINR", date(2026, 10, 19))
    assert [g["security_id"] for g in got] == ["1", "2"]
    assert got[0]["lot_size_known"] and not got[1]["lot_size_known"] and got[1]["lot_size"] == 1000


def test_pnl_multiplier_uses_the_contract_spec_not_the_master_lot():
    assert ci.UNDERLYINGS["GOLDM"].pnl_multiplier() == 10        # 100 g lot quoted per 10 g
    assert ci.UNDERLYINGS["CRUDEOIL"].pnl_multiplier(1) == 100   # the master said lot 1 on 2026-10-19
    assert ci.UNDERLYINGS["USDINR"].pnl_multiplier() == 1000


def test_future_expiring_today_is_rolled_past_and_crudeoilm_is_not_crudeoil():
    rows = [_row("CRUDEOIL", "FUTCOM", "MCX", "2026-10-19", "1", "1"), _row("CRUDEOIL", "FUTCOM", "MCX", "2026-11-19", "2", "1"),
            _row("CRUDEOILM", "FUTCOM", "MCX", "2026-11-19", "3", "10")]
    got = ci.nearest_futures(rows, "CRUDEOIL", date(2026, 10, 19))
    assert [g["security_id"] for g in got] == ["2"]


def test_currency_future_found_when_underlying_column_is_blank_or_oddly_formatted():
    base = {"INSTRUMENT": "FUTCUR", "EXCH_ID": "NSE", "SM_EXPIRY_DATE": "2026-10-28", "SECURITY_ID": "55", "LOT_SIZE": "1"}
    for extra in ({"UNDERLYING_SYMBOL": "USDINR"}, {"UNDERLYING_SYMBOL": "", "SYMBOL_NAME": "USDINR"},
                  {"UNDERLYING_SYMBOL": "USD-INR"}, {"UNDERLYING_SYMBOL": "", "DISPLAY_NAME": "USDINR 28 OCT FUT"}):
        got = ci.nearest_futures([{**base, **extra}], "USDINR", date(2026, 10, 19))
        assert got and got[0]["security_id"] == "55", extra
    other = {**base, "UNDERLYING_SYMBOL": "EURINR"}
    assert ci.nearest_futures([other], "USDINR", date(2026, 10, 19)) == []


def test_resolver_caches_for_the_day(tmp_path):
    calls = []

    async def fetch():
        calls.append(1)
        return "INSTRUMENT,EXCH_ID,UNDERLYING_SYMBOL,SM_EXPIRY_DATE,SECURITY_ID,LOT_SIZE\nFUTCOM,MCX,GOLDM,2026-12-04,7,100\n"

    path = str(tmp_path / "m.json")
    r = ci.ContractResolver(path, fetch)
    out = asyncio.run(r.resolve(["GOLDM"], date(2026, 10, 19)))
    assert out["GOLDM"][0]["security_id"] == "7"
    asyncio.run(ci.ContractResolver(path, fetch).resolve(["GOLDM"], date(2026, 10, 19)))
    assert len(calls) == 1
    assert json.load(open(path))["day"] == "2026-10-19"


def test_cx_settings_are_off_by_default():
    assert BY_KEY["cx_enabled"].default is False
    assert BY_KEY["cx_currency_enabled"].default is False and "USDINR" not in BY_KEY["cx_symbols"].default
    assert BY_KEY["cx_loss_cap_commodity"].default == 15000.0 and BY_KEY["cx_loss_cap_currency"].default == 5000.0


def test_no_live_currency_future_falls_back_to_the_options_underlying():
    stale = _row("USDINR", "FUTCUR", "NSE", "2024-08-28", "1026077", "1")
    opts = [dict(_row("USDINR", "OPTCUR", "NSE", exp, "9" + str(i), "1"), UNDERLYING_SECURITY_ID=uid)
            for i, (exp, uid) in enumerate([("2026-10-28", "20001.0"), ("2026-11-26", "20002"), ("2026-10-28", "20001")])]
    rows = [stale] + opts
    assert ci.nearest_futures(rows, "USDINR", date(2026, 10, 19)) == []
    got = ci.find_contracts(rows, "USDINR", date(2026, 10, 19))
    assert [(g["security_id"], g["expiry"], g["source"]) for g in got] == [("20001", "2026-10-28", "option_underlying"), ("20002", "2026-11-26", "option_underlying")]


def test_option_expiry_picks_the_future_it_is_written_on():
    cs = [{"security_id": "nov", "expiry": "2026-11-19"}, {"security_id": "dec", "expiry": "2026-12-18"}]
    assert ci.underlying_for_option_expiry(cs, "2026-11-17")["security_id"] == "nov"
    assert ci.underlying_for_option_expiry(cs, "2026-11-20")["security_id"] == "dec"
    assert ci.underlying_for_option_expiry(cs, "2027-01-01") is None
