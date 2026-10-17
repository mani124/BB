"""A restart must not hang on an open dashboard stream (the 2026-10-16 SIGKILL at 15:35)."""
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run(tmp_path, extra: list[str], wait: float) -> bool:
    """Start the app, open the SSE stream, send SIGTERM, return True if the process exited within `wait` seconds."""
    port = _free_port()
    env = dict(os.environ, BB_DATA_DIR=str(tmp_path), DASHBOARD_CAPABILITY="testkey")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), *extra],
                            cwd=os.path.dirname(os.path.dirname(__file__)), env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stream = None
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1).read()
                break
            except Exception:
                time.sleep(0.2)
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/signals/stream",
                                     headers={"X-Dashboard-Capability": "testkey"})
        stream = urllib.request.urlopen(req, timeout=5)
        stream.read(1)
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=wait)
            return True
        except subprocess.TimeoutExpired:
            return False
    finally:
        if stream is not None:
            stream.close()
        if proc.poll() is None:
            proc.kill()
        proc.wait()


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX signals")
def test_open_stream_does_not_block_shutdown_with_timeout_flag(tmp_path):
    assert _run(tmp_path, ["--timeout-graceful-shutdown", "2"], wait=15)
