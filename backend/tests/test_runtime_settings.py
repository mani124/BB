import pytest
from starlette.testclient import TestClient

from app.services.paper_trader import PaperTradingEngine
from app.services.runtime_settings import BY_KEY, DEFINITIONS, RuntimeSettings, SettingError, coerce


def test_every_definition_has_a_valid_default():
    for d in DEFINITIONS:
        assert coerce(d, d.default_value()) is not None


def test_keys_are_unique():
    assert len({d.key for d in DEFINITIONS}) == len(DEFINITIONS)


def test_set_validates_type_range_and_unknown_key(tmp_path):
    rs = RuntimeSettings(str(tmp_path / "s.db"))
    with pytest.raises(SettingError):
        rs.set("max_open_positions", -1)
    with pytest.raises(SettingError):
        rs.set("max_open_positions", 2.5)
    with pytest.raises(SettingError):
        rs.set("max_entry_spread_pct", 101)
    with pytest.raises(SettingError):
        rs.set("earnings_entry_time", "25:99")
    with pytest.raises(SettingError):
        rs.set("nope", 1)
    with pytest.raises(SettingError):
        rs.set("telemetry_enabled", "maybe")
    assert rs.set("max_open_positions", "5") == 5
    assert rs.set("telemetry_enabled", "off") is False
    assert rs.set("earnings_entry_time", "09:45") == "09:45"


def test_value_survives_restart_and_reset_returns_default(tmp_path):
    db = str(tmp_path / "s.db")
    rs = RuntimeSettings(db)
    default = rs.get("max_open_positions")
    rs.set("max_open_positions", default + 3)
    assert RuntimeSettings(db).get("max_open_positions") == default + 3
    assert rs.is_overridden("max_open_positions")
    assert rs.reset("max_open_positions") == default
    assert RuntimeSettings(db).get("max_open_positions") == default


def test_env_default_is_read_lazily(tmp_path, monkeypatch):
    rs = RuntimeSettings(str(tmp_path / "s.db"))
    monkeypatch.setattr("app.core.config.settings.MAX_OPEN_POSITIONS", 11)
    assert rs.get("max_open_positions") == 11
    rs.set("max_open_positions", 4)
    assert rs.get("max_open_positions") == 4


def test_set_many_is_all_or_nothing(tmp_path):
    rs = RuntimeSettings(str(tmp_path / "s.db"))
    before = rs.get("max_open_positions")
    with pytest.raises(SettingError):
        rs.set_many({"max_open_positions": 9, "max_entry_spread_pct": 500})
    assert rs.get("max_open_positions") == before


def test_changes_are_audited(tmp_path):
    rs = RuntimeSettings(str(tmp_path / "s.db"))
    old = rs.get("max_lots_per_trade")
    rs.set("max_lots_per_trade", 6, actor="tester")
    row = rs.audit(limit=1, key="max_lots_per_trade")[0]
    assert (row["old_value"], row["new_value"], row["actor"]) == (str(old), "6", "tester")


def test_bad_stored_value_does_not_block_startup(tmp_path):
    import sqlite3
    db = str(tmp_path / "s.db")
    RuntimeSettings(db)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO runtime_settings (key, value) VALUES ('max_open_positions', 'garbage')")
        c.execute("INSERT INTO runtime_settings (key, value) VALUES ('removed_key', '1')")
    rs = RuntimeSettings(db)
    assert rs.get("max_open_positions") == BY_KEY["max_open_positions"].default_value()


def test_engine_mirrors_default_lots_and_loss_limit(tmp_path):
    db = str(tmp_path / "e.db")
    e = PaperTradingEngine(db_path=db)
    e.runtime.set("daily_loss_limit", 777)
    assert e.get_portfolio().default_lots == 2
    assert e._daily_loss_limit == 777
    e2 = PaperTradingEngine(db_path=db)
    assert e2.get_portfolio().default_lots == 2 and e2._daily_loss_limit == 777
    with pytest.raises(SettingError):
        e.runtime.set("default_lots", 6)          # lots per entry are fixed at 2


def test_legacy_saved_values_are_adopted(tmp_path):
    from app.services.paper_storage import PaperStorage
    db = str(tmp_path / "legacy.db")
    st = PaperStorage(db)
    st.save_setting("default_lots", "4")
    st.save_setting("max_risk_per_trade", "12000")
    st.save_setting("daily_loss_limit", "5000")
    e = PaperTradingEngine(db_path=db)
    assert e.get_portfolio().default_lots == 2   # an old saved 4 is not honoured
    assert e.get_portfolio().max_risk_per_trade == 12000
    assert e._daily_loss_limit == 5000
    assert PaperTradingEngine(db_path=db)._daily_loss_limit == 5000


def test_api_roundtrip():
    from app.main import app
    from app.services.paper_trader import paper_trader
    client = TestClient(app)
    body = client.get("/api/settings").json()
    keys = {s["key"] for s in body["settings"]}
    assert {"daily_loss_limit", "max_lots_per_trade", "earnings_enabled"} <= keys
    try:
        r = client.put("/api/settings", json={"changes": {"max_lots_per_trade": 3}})
        assert r.status_code == 200
        assert next(s for s in r.json()["settings"] if s["key"] == "max_lots_per_trade")["value"] == 3
        assert client.put("/api/settings", json={"changes": {"max_lots_per_trade": -2}}).status_code == 422
        assert client.put("/api/settings", json={"changes": {"bogus": 1}}).status_code == 422
        assert client.get("/api/settings/audit?key=max_lots_per_trade").json()[0]["new_value"] == "3"
    finally:
        client.post("/api/settings/max_lots_per_trade/reset")
    assert paper_trader.runtime.get("max_lots_per_trade") == 0
    assert client.post("/api/settings/bogus/reset").status_code == 404
