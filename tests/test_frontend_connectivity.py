"""Real regression guard for the "UI shows Failed to fetch" class of bug.

The actual incident this responds to: `api/Dockerfile` never copied
`worker/` (imported by `api/routers/books.py`/`problem_sets.py` to
`.delay()` real Celery jobs) and `typst` was installed ad hoc in a dev
venv but never declared in `pyproject.toml` — so the built image looked
fine, but the CONTAINER crashed on startup with `ModuleNotFoundError`
before ever binding its port. A browser reports that identically to a
CORS rejection ("Failed to fetch"), which is why the initial diagnosis
reasonably suspected CORS first — curl doesn't apply same-origin-policy
at all, so it can't distinguish "server unreachable" from "server
reachable but CORS-blocked," and a curl-only check would have missed
this entirely.

This builds the REAL api Docker image, runs it for real, confirms the
container is actually still running (not just that /healthz answered
once, which can race a crash-after-import-succeeds failure), and then
uses a REAL headless browser — navigated to a page served on its own
real HTTP origin, not `file://` or `about:blank` — to fetch the API
across origins. That's the only way to genuinely exercise the browser's
CORS enforcement rather than assume the `allow_origins=["*"]` config
works because it looks permissive.

Marked `@pytest.mark.e2e` (needs Docker) — excluded from the default run,
same as test_api_e2e.py. Doesn't need a Celery worker or any LLM call, so
it's much cheaper/faster than the full upload-to-PDF e2e test; run it
alone with `pytest tests/test_frontend_connectivity.py -m e2e -v`.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import socket
import subprocess
import threading
import time
from functools import partial
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright

from practice_forge.config import REPO_ROOT

pytestmark = pytest.mark.e2e

API_URL = "http://localhost:8000"
API_CONTAINER_NAME = "practice-forge-api-1"
STARTUP_TIMEOUT_S = 90


def _wait_for_healthz(timeout_s: float) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{API_URL}/healthz", timeout=2).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(1)
    return False


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


class _QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def test_api_container_builds_and_stays_running() -> None:
    """The exact incident: the image built fine and `docker compose up`
    reported "Started", but the container crashed seconds later. Checking
    real container state (not just one healthz response) is what actually
    catches that — and on failure, dumps the real crash logs so the next
    regression is diagnosed in seconds, not by re-deriving all of this."""
    subprocess.run(["docker", "compose", "build", "api"], cwd=str(REPO_ROOT), check=True)
    subprocess.run(["docker", "compose", "up", "-d", "api"], cwd=str(REPO_ROOT), check=True)

    healthy = _wait_for_healthz(STARTUP_TIMEOUT_S)

    status = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", API_CONTAINER_NAME],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    if status != "true" or not healthy:
        logs = subprocess.run(
            ["docker", "logs", "--tail", "40", API_CONTAINER_NAME],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        pytest.fail(
            f"api container did not stay up and healthy (running={status}, "
            f"healthz_ok={healthy}). Real container logs:\n{logs}"
        )


def test_real_browser_can_fetch_api_across_origins(tmp_path: Path) -> None:
    """Reproduces the exact browser-visible symptom: a page served on its
    own real HTTP origin (a fresh port — the CORS config under test,
    `allow_origins=["*"]`, is meant to cover ANY dev-server port, not just
    whichever one :3000/:3001 happen to be free at test time) fetching
    the real api container across origins. curl cannot exercise this at
    all, which is exactly why a curl-only check missed the incident."""
    assert _wait_for_healthz(30), "api not reachable before running the browser check"

    html = tmp_path / "index.html"
    html.write_text(
        """<!doctype html><html><body><div id="result">pending</div>
<script>
  fetch("http://localhost:8000/api/books")
    .then((r) => r.json())
    .then((data) => {
      document.getElementById("result").textContent = JSON.stringify({ok: true, count: data.length});
    })
    .catch((err) => {
      document.getElementById("result").textContent = JSON.stringify({ok: false, error: String(err)});
    });
</script></body></html>""",
        encoding="utf-8",
    )

    port = _free_port()
    handler = partial(_QuietHTTPHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("localhost", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            page.goto(f"http://localhost:{port}/index.html")
            page.wait_for_function(
                "document.getElementById('result').textContent !== 'pending'", timeout=10_000
            )
            result_text = page.locator("#result").text_content()
            browser.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result_text is not None
    result = json.loads(result_text)
    assert result["ok"], (
        f"a real browser on http://localhost:{port} could not fetch the api "
        f"(this is the exact 'Failed to fetch' symptom): {result.get('error')}"
    )
    assert result["count"] > 0, "api responded but returned no books — check the real DB state"
