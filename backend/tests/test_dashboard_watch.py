def test_watch_keeps_true_stages_and_labels_previews():
    from app.services.dashboard_read import build_dashboard_watch
    watch = build_dashboard_watch(
        {"active_mode": "demo", "last_scan_time": "09:34:00", "signals": [
            {"id": "sig-1", "symbol": "NIFTY", "setup_type": "Setup 1", "timestamp": "2026-10-19T09:30:00+05:30", "is_confirmed": True, "rationale": "Band break"},
        ]},
        {"summary": {"enabled": True, "last_cycle": {"at": "2026-10-19T09:36:00+05:30", "status": "ok"}},
         "candidates": [{"symbol": "CRUDEOIL", "setup": "Setup 17", "ready": False, "code": "LOSS_CAP", "detail": "Limit reached"}]},
        {"summary": {"enabled": True, "last_cycle": {"at": "2026-10-19T09:37:00+05:30", "status": "ok"}},
         "candidates": [{"symbol": "INFY", "mode": "MODE_A", "ready": True, "code": "READY", "metrics": {"iv": 20}}]},
        observed_at="2026-10-19T09:38:00+05:30",
    )
    assert len(watch["candidates"]) == 3
    assert {c["book"] for c in watch["candidates"]} == {"paper", "cx", "earnings"}
    cx = next(c for c in watch["candidates"] if c["book"] == "cx")
    assert cx["is_preview"] is True
    assert cx["block_reason"] == "Limit reached"
    earnings = next(c for c in watch["candidates"] if c["book"] == "earnings")
    assert earnings["is_preview"] is True
    assert earnings["checks"][0]["value"] == 20


def test_watch_isolates_failed_source_and_never_calls_missing_time_fresh():
    from app.services.dashboard_read import build_dashboard_watch
    watch = build_dashboard_watch(
        {"active_mode": "demo", "signals": []},
        {"_error": "CX provider failed"},
        {"summary": {"enabled": True, "last_cycle": {"at": "2026-10-19T09:37:00+05:30", "status": "ok"}}, "candidates": []},
        observed_at="2026-10-19T09:38:00+05:30",
    )
    sources = {s["book"]: s for s in watch["sources"]}
    assert sources["paper"]["state"] == "idle"
    assert sources["paper"]["message"] == "No evaluation recorded yet"
    assert sources["paper"]["as_of"] is None
    assert "setup16" not in sources
    assert sources["cx"]["state"] == "error"
    assert sources["earnings"]["state"] == "ready"


def test_empty_scanner_uses_full_scan_timestamp_when_available():
    from app.services.dashboard_read import build_dashboard_watch

    watch = build_dashboard_watch(
        {"active_mode": "demo", "last_scan_at": "2026-10-19T09:37:00+05:30", "signals": []},
        {}, {}, observed_at="2026-10-19T09:38:00+05:30",
    )
    paper = next(source for source in watch["sources"] if source["book"] == "paper")
    assert paper["as_of"] == "2026-10-19T09:37:00+05:30"
    assert paper["state"] == "ready"


def test_scanner_error_state_does_not_look_ready_with_recent_scan():
    from app.services.dashboard_read import build_dashboard_watch
    watch = build_dashboard_watch(
        {"active_mode": "error", "last_scan_at": "2026-10-19T09:37:00+05:30", "signals": []},
        {}, {}, observed_at="2026-10-19T09:38:00+05:30")
    paper = next(source for source in watch["sources"] if source["book"] == "paper")
    assert paper["state"] == "error"


def test_watch_handles_mixed_naive_and_timezone_aware_times():
    from app.services.dashboard_read import build_dashboard_watch
    watch = build_dashboard_watch(
        {"active_mode": "demo", "last_scan_at": "2026-10-19T09:37:00", "signals": []},
        {}, {}, observed_at="2026-10-19T09:38:00+05:30")
    paper = next(source for source in watch["sources"] if source["book"] == "paper")
    assert paper["state"] == "ready"


def test_no_credentials_is_unhealthy_and_candidate_ids_survive_reordering():
    from app.services.dashboard_read import build_dashboard_watch
    a = {"symbol": "CRUDEOIL", "setup": "Setup 17", "side": "CE", "bar_time": "09:30", "code": "READY"}
    b = {"symbol": "CRUDEOIL", "setup": "Setup 17", "side": "PE", "bar_time": "09:35", "code": "READY"}
    payload = {"summary": {"enabled": True, "last_cycle": {"at": "2026-10-19T09:37:00+05:30", "status": "no_credentials"}},
               "candidates": [a, b]}
    first = build_dashboard_watch({}, payload, {}, observed_at="2026-10-19T09:38:00+05:30")
    payload["candidates"] = [b, a]
    second = build_dashboard_watch({}, payload, {}, observed_at="2026-10-19T09:38:00+05:30")
    source = next(source for source in first["sources"] if source["book"] == "cx")
    assert source["state"] == "error"
    assert "login" in source["message"].lower()
    assert {candidate["id"] for candidate in first["candidates"]} == {candidate["id"] for candidate in second["candidates"]}
