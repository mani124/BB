import logging
import threading

from app.services import notifier as nmod
from app.services.notifier import Notifier, TelegramChannel


class Rec:
    def __init__(self, fail=False, gate=None):
        self.sent, self.fail, self.gate = [], fail, gate
        self.done = threading.Event()

    def send(self, text):
        if self.gate:
            self.gate.wait(2)
        if self.fail:
            raise RuntimeError("boom https://api.telegram.org/bot123:SECRET/sendMessage")
        self.sent.append(text)
        self.done.set()


def drain(n):
    n._pool.shutdown(wait=True)


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    n = Notifier()
    assert not n.enabled
    assert n.notify("x", "hi") is False


def test_enabled_with_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")
    assert Notifier().enabled


def test_sends_and_dedupes():
    t = [0.0]
    ch = Rec()
    n = Notifier([ch], clock=lambda: t[0])
    assert n.notify("e", "one", min_interval=100)
    assert not n.notify("e", "two", min_interval=100)
    assert n.notify("other", "three", min_interval=100)
    t[0] = 101
    assert n.notify("e", "four", min_interval=100)
    drain(n)
    assert ch.sent == ["one", "three", "four"]


def test_does_not_block_caller():
    gate = threading.Event()
    ch = Rec(gate=gate)
    n = Notifier([ch])
    assert n.notify("e", "slow")  # returns while the send is still blocked
    assert ch.sent == []
    gate.set()
    drain(n)
    assert ch.sent == ["slow"]


def test_failure_is_swallowed_and_token_not_logged(caplog):
    n = Notifier([Rec(fail=True)])
    with caplog.at_level(logging.DEBUG):
        n.notify("e", "x")
        drain(n)
    assert "SECRET" not in caplog.text
    assert "not delivered" in caplog.text


def test_queue_is_bounded():
    gate = threading.Event()
    n = Notifier([Rec(gate=gate)])
    results = [n.notify(f"e{i}", "x") for i in range(nmod.MAX_QUEUED + 5)]
    assert results.count(True) == nmod.MAX_QUEUED
    gate.set()
    drain(n)


def test_telegram_request(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"], seen["body"], seen["timeout"] = req.full_url, req.data, timeout

        class R:
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return R()

    monkeypatch.setattr(nmod.urllib.request, "urlopen", fake_urlopen)
    TelegramChannel("TOK", "42").send("hello")
    assert seen["url"] == "https://api.telegram.org/botTOK/sendMessage"
    assert b'"chat_id": "42"' in seen["body"] and b"hello" in seen["body"]
    assert seen["timeout"] == nmod.SEND_TIMEOUT_SECONDS


def test_feed_transitions(monkeypatch):
    calls = []
    monkeypatch.setattr(nmod, "notify", lambda ev, text, **kw: calls.append(ev))
    monkeypatch.setattr(nmod, "_feed_state", "idle")
    for m in ["demo", "closed", "live", "closed", "stale", "error", "live", "live"]:
        nmod.report_feed_mode(m)
    assert calls == ["feed_down", "feed_up"]


def test_position_close_alert(monkeypatch):
    from app.services import paper_exits
    from app.services.paper_trader import PaperTradingEngine
    from tests.test_p0_session_guard import make_signal
    from app.core.config import settings

    monkeypatch.setattr(settings, "REENTRY_COOLDOWN_SECONDS", 0)
    calls = []
    monkeypatch.setattr(paper_exits, "notify", lambda ev, text, **kw: calls.append((ev, text, kw)))
    eng = PaperTradingEngine()
    pos = eng.open_position_from_signal(make_signal("N1", entry=43.6), feed_mode="demo")
    eng._finalize_closed_position(pos, 40.0, "STOPPED_OUT", "Stop Loss Hit", "10:00:00")
    assert len(calls) == 1
    ev, text, kw = calls[0]
    assert ev == "position_closed" and text.startswith("Stop hit") and kw["dedupe_key"] == f"closed:{pos.id}"
    eng._finalize_closed_position(pos, 50.0, "CLOSED", "EOD square-off", "15:20:00")
    assert len(calls) == 1  # manual / EOD closes are not alerts
