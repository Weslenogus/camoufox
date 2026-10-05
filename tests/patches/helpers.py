"""
Shared helpers for patch verification tests.

Run tests from dvsa-bot to get the right venv:
    cd ~/20tech/drivingtest/dvsa-bot
    uv run python ~/20tech/oss/camoufox/tests/patches/<test>.py
"""

from contextlib import asynccontextmanager
from typing import Any, Dict, Optional


MAX_PRESET_ATTEMPTS = 15


@asynccontextmanager
async def launch_camoufox(
    os: str = "macos",
    headless: bool = True,
    max_attempts: int = MAX_PRESET_ATTEMPTS,
):
    """
    Launch Camoufox with a random preset, retrying on WebGL mismatches.

    Yields (page, fingerprint_config) — the config dict lets tests check
    what values were sent to the browser.

    About half of get_random_preset() calls produce a WebGL vendor/renderer
    combo that doesn't exist in the sample data. This wrapper retries
    transparently so every test doesn't need its own retry loop.
    """
    from camoufox.async_api import AsyncCamoufox
    from camoufox.fingerprints import generate_context_fingerprint, get_random_preset

    last_error: Optional[Exception] = None
    for attempt in range(max_attempts):
        preset = get_random_preset(os=os)
        fp = generate_context_fingerprint(preset=preset)
        try:
            async with AsyncCamoufox(
                fingerprint_preset=fp["preset"],
                headless=headless,
                os=os,
            ) as browser:
                context = await browser.new_context(**fp["context_options"])
                await context.add_init_script(fp["init_script"])
                page = await context.new_page()
                await page.goto("about:blank")
                yield page, fp["config"]
                return
        except ValueError as e:
            if "WebGL" in str(e):
                last_error = e
                continue
            raise

    raise RuntimeError(
        f"Could not find a valid preset after {max_attempts} attempts"
    ) from last_error


# ---------------------------------------------------------------------------
# Android device profile guards (tests/patches/android-*.py)
#
# These drive the raw binary with CAMOU_CONFIG, the way touchscreen-digitizer.py
# does, because a device profile is a CAMOU_CONFIG feature: the Python
# package's desktop fingerprint generation would override it key by key.
#
# Every android guard checks two things: that {"device:profile": "pixel10"}
# produces the Android value, and that a launch *without* the profile is left
# exactly as it was. The second half is what keeps a phone-only change from
# leaking into every ordinary desktop launch.
# ---------------------------------------------------------------------------

import json as _json
import os as _os
import threading as _threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path as _Path
from typing import Callable, List, Tuple

REPO_ROOT = _Path(__file__).resolve().parents[2]

PIXEL10: Dict[str, Any] = {"device:profile": "pixel10"}


@asynccontextmanager
async def launch_raw(binary: _Path, config: Dict[str, Any],
                     prefs: Optional[Dict[str, Any]] = None, **context_options):
    """Launch the binary with `config` as CAMOU_CONFIG (and `prefs` as user
    prefs, if given); yield a fresh page."""
    from playwright.async_api import async_playwright

    env = dict(_os.environ)
    env["CAMOU_CONFIG_1"] = _json.dumps(config)
    async with async_playwright() as p:
        browser = await p.firefox.launch(
            executable_path=str(binary), headless=True, env=env,
            firefox_user_prefs=prefs or {},
        )
        try:
            context = await browser.new_context(**context_options)
            page = await context.new_page()
            yield page
        finally:
            await browser.close()


class PageServer:
    """
    A loopback HTTP server for guards that need a real origin: workers, iframes,
    secure-context APIs, and request headers. http://localhost is a secure
    context, so SecureContext-only interfaces are exposed on it.

    `routes` maps a path to (content type, body). Every request's headers are
    recorded, in order, in `requests` as (path, {lower-cased name: value}).
    """

    def __init__(self, routes: Dict[str, Tuple[str, str]]):
        self.routes = routes
        self.requests: List[Tuple[str, Dict[str, str]]] = []
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 (http.server naming)
                path = self.path.split("?", 1)[0]
                server.requests.append(
                    (path, {k.lower(): v for k, v in self.headers.items()})
                )
                ctype, body = server.routes.get(path, ("text/plain", "not found"))
                data = body.encode()
                self.send_response(200 if path in server.routes else 404)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = _threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()

    def url(self, path: str = "/") -> str:
        return f"http://localhost:{self._httpd.server_address[1]}{path}"

    def headers_for(self, path: str) -> List[Dict[str, str]]:
        return [h for p, h in self.requests if p == path]


def compare(actual: Dict[str, Any], expected: Dict[str, Any]) -> bool:
    """Print a per-signal table. True only if every expected signal matches."""
    missing = sorted(set(expected) - set(actual))
    if missing:
        print(f"  FAIL: probe never collected: {', '.join(missing)}")
        return False
    width = max(len(k) for k in expected)
    failures = 0
    for name, want in expected.items():
        got = actual[name]
        ok = want(got) if callable(want) else want == got
        failures += not ok
        mark = "ok  " if ok else "FAIL"
        shown = _json.dumps(got) if not isinstance(got, str) else repr(got)
        detail = shown if ok or callable(want) else f"{shown} (expected {_json.dumps(want)})"
        print(f"    [{mark}] {name:<{width}}  {detail}")
    print(f"\n  {len(expected) - failures}/{len(expected)} signals match")
    return failures == 0


def run_guard(main: Callable) -> None:
    """Resolve the binary, run `main(binary)`, exit 0/1 like every guard."""
    import asyncio
    import sys

    binary = resolve_binary(sys.argv)
    if binary is None or not binary.exists():
        print(f"FATAL: no camoufox binary found (looked for {binary})")
        sys.exit(1)
    print(f"Binary: {binary}")
    sys.exit(0 if asyncio.run(main(binary)) else 1)

# --- chrome-context inspection (Marionette) on a hidden display -----------------
#
# Some guards assert browser-UI state a page cannot read (a URL-bar label, a chrome
# overlay, the graphics decision log). They drive Marionette's chrome context.
# Marionette itself shows the remote-control cue, so these always run on a PRIVATE
# Xvfb display -- never on a real screen.

import contextlib
import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Iterator, List


def resolve_binary(argv: Optional[List[str]] = None) -> Path:
    """The camoufox binary under test: `--binary <path>` in argv, else the runner's
    CAMOUFOX_EXECUTABLE_PATH, else CAMOUFOX_BINARY, else the newest in-tree Linux
    build (never another target's objdir, which cannot execute here)."""
    if argv and "--binary" in argv:
        return Path(argv[argv.index("--binary") + 1]).resolve()
    for var in ("CAMOUFOX_EXECUTABLE_PATH", "CAMOUFOX_BINARY"):
        if os.environ.get(var):
            return Path(os.environ[var]).resolve()
    root = Path(__file__).resolve().parents[2]
    matches = sorted(root.glob("camoufox-*/obj-*-linux-gnu/dist/bin/camoufox-bin"))
    if not matches:
        raise SystemExit("no camoufox binary: set CAMOUFOX_EXECUTABLE_PATH")
    return matches[-1]


@contextlib.contextmanager
def hidden_display() -> Iterator[str]:
    """A private Xvfb display for the duration of the block."""
    if not shutil.which("Xvfb"):
        raise SystemExit("Xvfb is required for this guard")
    for n in range(140, 160):
        if not os.path.exists(f"/tmp/.X11-unix/X{n}"):
            break
    display = f":{n}"
    proc = subprocess.Popen(["Xvfb", display, "-screen", "0", "1400x900x24", "-nolisten", "tcp"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    try:
        yield display
    finally:
        proc.terminate()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Marionette:
    """Minimal Marionette client: length-prefixed JSON over TCP, chrome context."""

    def __init__(self, port: int, timeout: float = 60):
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.5)
        self.sock.settimeout(timeout)
        self._id = 0
        self._recv()  # server hello
        self.call("WebDriver:NewSession", {"capabilities": {}})
        self.call("Marionette:SetContext", {"value": "chrome"})

    def _recv(self):
        buf = b""
        while b":" not in buf:
            buf += self.sock.recv(1)
        size, rest = buf.split(b":", 1)
        while len(rest) < int(size):
            rest += self.sock.recv(int(size) - len(rest))
        return json.loads(rest)

    def call(self, command: str, params: dict):
        self._id += 1
        data = json.dumps([0, self._id, command, params]).encode()
        self.sock.sendall(str(len(data)).encode() + b":" + data)
        while True:
            msg = self._recv()
            if isinstance(msg, list) and msg[1] == self._id:
                if msg[2]:
                    raise RuntimeError(f"{command}: {msg[2]}")
                return msg[3]

    def js(self, script: str):
        """Run chrome-context JS (in the browser window) and return its JSON value."""
        return self.call("WebDriver:ExecuteScript", {"script": script, "args": []}).get("value")

    def close(self):
        with contextlib.suppress(Exception):
            self.sock.close()


def marionette_args() -> List[str]:
    return ["--marionette", "--remote-allow-system-access"]
