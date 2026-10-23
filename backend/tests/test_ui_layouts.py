import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.ui_store import MAX_SNAPSHOTS, UiStore, UiStoreError

client = TestClient(app)
BODY = {"schema_version": 1, "name": "Trading", "root": {"type": "group", "panels": [{"id": "signals"}]}}


@pytest.fixture
def store():
    d = tempfile.mkdtemp(prefix="ui-store-")
    return UiStore(os.path.join(d, "t.db"), snapshot_gap_s=0)


def test_put_get_round_trip(store):
    row = store.put("workspace:Trading", BODY, 1)
    assert row["kind"] == "workspace" and row["body"] == BODY and row["schema_version"] == 1
    assert store.get("workspace:Trading")["body"] == BODY
    assert [r["name"] for r in store.list()] == ["workspace:Trading"]


def test_snapshots_keep_the_last_twenty_and_evict_the_oldest(store):
    for i in range(MAX_SNAPSHOTS + 3):
        store.put("custom:A", {**BODY, "n": i}, 1)
    snaps = store.snapshots("custom:A")
    assert len(snaps) == MAX_SNAPSHOTS
    # the oldest snapshots (bodies 0 and 1) are gone; ids are strictly newest-first
    ids = [s["id"] for s in snaps]
    assert ids == sorted(ids, reverse=True)
    with store._conn() as conn:
        bodies = [json.loads(r["body"])["n"] for r in conn.execute("SELECT body FROM ui_layout_snapshots WHERE name = 'custom:A';")]
    assert 0 not in bodies and 1 not in bodies


def test_snapshots_are_rate_limited_by_the_gap():
    d = tempfile.mkdtemp(prefix="ui-store-")
    s = UiStore(os.path.join(d, "t.db"), snapshot_gap_s=60)
    for i in range(5):
        s.put("custom:A", {**BODY, "n": i}, 1)
    assert len(s.snapshots("custom:A")) == 1  # only the pre-edit state of this editing burst


def test_restore_returns_the_body_and_keeps_the_replaced_state(store):
    store.put("custom:A", {**BODY, "n": 1}, 1)
    store.put("custom:A", {**BODY, "n": 2}, 1)
    snap = store.snapshots("custom:A")[0]
    before = len(store.snapshots("custom:A"))
    row = store.restore("custom:A", snap["id"])
    assert row["body"]["n"] == 1
    assert len(store.snapshots("custom:A")) == before + 1


def test_oversize_body_is_413(store):
    with pytest.raises(UiStoreError) as e:
        store.put("custom:A", {"blob": "x" * (257 * 1024)}, 1)
    assert e.value.status == 413


def test_delete_only_custom(store):
    store.put("workspace:Trading", BODY, 1)
    with pytest.raises(UiStoreError) as e:
        store.delete("workspace:Trading")
    assert e.value.status == 403
    store.put("custom:Mine", BODY, 1)
    assert store.delete("custom:Mine") is True
    assert store.get("custom:Mine") is None


@pytest.mark.parametrize("name", ["bad/name", "workspace:<script>", "", "x" * 90, "plain"])
def test_invalid_names_are_422(store, name):
    with pytest.raises(UiStoreError) as e:
        store.put(name, BODY, 1)
    assert e.value.status == 422


def test_nan_is_rejected(store):
    with pytest.raises(ValueError):
        store.put("custom:A", {"x": float("nan")}, 1)


def test_restore_unknown_snapshot_is_404(store):
    with pytest.raises(UiStoreError) as e:
        store.restore("custom:A", 999)
    assert e.value.status == 404


# --- HTTP ------------------------------------------------------------------------------------------

def _put(name, body=BODY, version=1, **kw):
    return client.put(f"/api/ui/layouts/{name}", json={"kind": "custom", "schema_version": version, "body": body}, **kw)


def test_api_round_trip_and_list():
    r = _put("custom:ApiRound")
    assert r.status_code == 200 and r.json()["body"] == BODY
    rows = client.get("/api/ui/layouts").json()
    assert any(x["name"] == "custom:ApiRound" for x in rows)


def test_api_bad_schema_version_is_422():
    assert _put("custom:V", version="x").status_code == 422
    assert client.put("/api/ui/layouts/custom:V", json={"kind": "custom", "body": BODY}).status_code == 422


def test_api_oversize_is_413():
    assert _put("custom:Big", body={"blob": "x" * (257 * 1024)}).status_code == 413


def test_api_delete_workspace_is_403_and_custom_ok():
    assert _put("workspace:Risk").status_code == 200
    assert client.delete("/api/ui/layouts/workspace:Risk").status_code == 403
    assert _put("custom:Del").status_code == 200
    assert client.delete("/api/ui/layouts/custom:Del").json() == {"deleted": True}


def test_api_invalid_name_chars_is_422():
    assert _put("custom:bad;name").status_code == 422


def test_api_snapshots_and_restore():
    _put("custom:Snap", body={**BODY, "n": 1})
    _put("custom:Snap", body={**BODY, "n": 2})
    snaps = client.get("/api/ui/layouts/custom:Snap/snapshots").json()
    assert snaps
    r = client.post(f"/api/ui/layouts/custom:Snap/restore/{snaps[0]['id']}")
    assert r.status_code == 200 and r.json()["body"]["n"] == 1
    assert client.post("/api/ui/layouts/custom:Snap/restore/99999").status_code == 404


def test_api_requires_capability():
    h = {"X-Omit-Capability": "1"}
    assert client.get("/api/ui/layouts", headers=h).status_code == 401
    assert client.put("/api/ui/layouts/custom:X", json={"kind": "custom", "schema_version": 1, "body": BODY}, headers=h).status_code == 401
    assert client.delete("/api/ui/layouts/custom:X", headers=h).status_code == 401
