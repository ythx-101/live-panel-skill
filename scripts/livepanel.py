"""Shared helpers: build the page from template + config, and drive Chrome over the DevTools pipe (standard library only)."""
import base64, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = ROOT / "assets" / "template.html"
CHROME_NAMES = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "microsoft-edge"]

# macOS app-bundle locations: the CLI names above are Linux conventions and shutil.which() misses them on macOS,
# where the browser only lives inside the .app (or as a Homebrew chromium symlink that exits immediately).
CHROME_MAC_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]


def find_exe(explicit, names, what):
    if explicit:
        p = shutil.which(explicit) or (explicit if os.path.exists(explicit) else None)
        if p:
            return p
        sys.exit(f"{what} not found: {explicit}")
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for p in CHROME_MAC_PATHS:
        if os.path.exists(p):
            return p
    sys.exit(f"{what} not found on PATH (tried {', '.join(names)}) or in /Applications; pass it explicitly")


def find_chrome(explicit):
    """Browser lookup that works on macOS: prefer a real /Applications .app (Homebrew's `chromium` shim on PATH
    often launches then dies on the DevTools pipe), then fall back to PATH names."""
    if explicit:
        p = shutil.which(explicit) or (explicit if os.path.exists(explicit) else None)
        if p:
            return p
        sys.exit(f"Chrome not found: {explicit}")
    for p in CHROME_MAC_PATHS:
        if os.path.exists(p):
            return p
    return find_exe(None, CHROME_NAMES, "Chrome")


CANVAS_PRESETS = {"4:5": (1200, 1500), "3:4": (1080, 1440), "1:1": (1080, 1080)}


def canvas(cfg):
    """(width, height, duration, fps) from a config, honouring canvas.preset."""
    cv = cfg.get("canvas", {})
    pw, ph = CANVAS_PRESETS.get(cv.get("preset"), (1200, 1500))
    return cv.get("width", pw), cv.get("height", ph), cv.get("duration", 30), cv.get("fps", 30)


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_page(config_path, out_path, template=None):
    """Write a self-contained HTML file: template with the JSON config embedded. Returns the config dict."""
    cfg = load_config(config_path)
    tpl = Path(template or DEFAULT_TEMPLATE).read_text(encoding="utf-8")
    blob = json.dumps(cfg, ensure_ascii=False).replace("</", "<\\/")
    tag = f'<script id="live-config" type="application/json">{blob}</script>'
    if "<!--LIVE_CONFIG-->" not in tpl:
        sys.exit("template has no <!--LIVE_CONFIG--> placeholder")
    Path(out_path).write_text(tpl.replace("<!--LIVE_CONFIG-->", tag), encoding="utf-8")
    return cfg


class Chrome:
    """Headless Chrome driven through --remote-debugging-pipe (no websocket, no third-party packages)."""

    def __init__(self, chrome, width, height, no_sandbox=None):
        self.tmp = tempfile.mkdtemp(prefix="livepanel-")
        r1, w1 = os.pipe()   # we write -> chrome fd 3
        r2, w2 = os.pipe()   # chrome fd 4 -> we read
        args = [chrome, "--headless=new", "--remote-debugging-pipe", f"--user-data-dir={self.tmp}", "--no-first-run",
                "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1", "--font-render-hinting=none",
                "--allow-file-access-from-files", "--disable-background-timer-throttling", "--mute-audio", "about:blank"]
        if no_sandbox or (no_sandbox is None and hasattr(os, "geteuid") and os.geteuid() == 0):
            args.insert(1, "--no-sandbox")
        env = dict(os.environ, LP_R=str(r1), LP_W=str(w2))
        self.proc = subprocess.Popen(["sh", "-c", 'exec "$@" 3<&"$LP_R" 4>&"$LP_W"', "sh"] + args, pass_fds=(r1, w2), env=env,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.close(r1); os.close(w2)
        self.wf = os.fdopen(w1, "wb", buffering=0); self.rf = os.fdopen(r2, "rb", buffering=0)
        self.buf = b""; self.n = 0
        tid = self.call("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.sid = self.call("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
        self.cmd("Page.enable")
        self.cmd("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})

    def call(self, method, params=None, session=None):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.wf.write(json.dumps(msg).encode() + b"\0")
        while True:
            while b"\0" not in self.buf:
                chunk = os.read(self.rf.fileno(), 1 << 20)
                if not chunk:
                    raise RuntimeError("Chrome closed the pipe")
                self.buf += chunk
            raw, self.buf = self.buf.split(b"\0", 1)
            m = json.loads(raw)
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(f"{method}: {m['error']}")
                return m.get("result", {})

    def cmd(self, method, params=None):
        return self.call(method, params, self.sid)

    def eval(self, expr):
        r = self.cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            raise RuntimeError(f"js error: {r['exceptionDetails']}")
        return r["result"].get("value")

    def open(self, url, timeout=20):
        self.cmd("Page.navigate", {"url": url})
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                if self.eval("window.__ready===true"):
                    err = self.eval("window.__error||''")
                    if err:
                        raise RuntimeError("page error: " + err)
                    return
                err = self.eval("window.__error||''")
                if err:
                    raise RuntimeError("page error: " + err)
            except RuntimeError as e:
                if "page error" in str(e):
                    raise
            time.sleep(0.1)
        raise RuntimeError("page did not become ready (check the config JSON)")

    def seek(self, t):
        self.eval(f"window.seek({t!r})")

    def shot(self):
        return base64.b64decode(self.cmd("Page.captureScreenshot", {"format": "png"})["data"])

    def close(self):
        try:
            self.proc.terminate(); self.proc.wait(5)
        except Exception:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
