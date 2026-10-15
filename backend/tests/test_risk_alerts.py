from app.services import notifier
from app.services.notifier import Notifier, risk_event_alert


class Rec:
    def __init__(self):
        self.sent = []

    def send(self, text):
        self.sent.append(text)


def _patch(monkeypatch):
    ch = Rec()
    n = Notifier(channels=[ch])
    monkeypatch.setattr(notifier, "notifier", n)
    return ch, n


def _drain(n):
    n._pool.shutdown(wait=True)


def test_loss_cap_event_sends_alert(monkeypatch):
    ch, n = _patch(monkeypatch)
    risk_event_alert("loss_cap_tripped", {"book": "live", "day_pnl": -25000, "limit": 24000, "date": "2026-10-15"})
    _drain(n)
    assert len(ch.sent) == 1 and "loss cap" in ch.sent[0] and "live" in ch.sent[0]


def test_kill_switch_events_send_alerts(monkeypatch):
    ch, n = _patch(monkeypatch)
    risk_event_alert("kill_switch_engaged", {})
    risk_event_alert("kill_switch_released", {})
    _drain(n)
    assert len(ch.sent) == 2 and "ENGAGED" in ch.sent[0] and "released" in ch.sent[1]


def test_unknown_event_is_ignored(monkeypatch):
    ch, n = _patch(monkeypatch)
    risk_event_alert("something_else", {})
    _drain(n)
    assert ch.sent == []


def test_engine_emits_to_handler(tmp_path, monkeypatch):
    from app.services.paper_trader import PaperTradingEngine
    ch, n = _patch(monkeypatch)
    e = PaperTradingEngine(db_path=str(tmp_path / "t.db"))
    e.on_risk_event = risk_event_alert
    e.set_kill_switch(True)
    _drain(n)
    assert any("ENGAGED" in t for t in ch.sent)
