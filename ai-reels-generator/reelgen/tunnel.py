"""Open the app from anywhere (the office, mobile data) without opening a port on the home router:
Cloudflare Tunnel. `cloudflared` on this computer dials out to Cloudflare and gets an https link;
nothing listens on the internet, and the phone needs only Safari.

REEL_TUNNEL=quick      a free trycloudflare.com link, no account (a new link each time the app starts:
                       it's sent on Telegram when set up, shown in Settings and saved in <output>/public_url.txt)
REEL_TUNNEL_TOKEN=...  a named tunnel from a Cloudflare account with your own domain: a fixed link
                       (REEL_PUBLIC_URL), and Cloudflare Access can add an email code in front of it.

The app refuses to go public without a PIN of at least 6 characters (server.require_pin and the
lockouts in server.login protect it).
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .config import Config

log = logging.getLogger(__name__)

QUICK_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
WINDOWS_PATHS = (r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe")
MIN_PIN = 6

state = {"url": "", "error": ""}


def cloudflared() -> str | None:
    return shutil.which("cloudflared") or next((p for p in WINDOWS_PATHS if Path(p).exists()), None)


def wanted(cfg: Config) -> bool:
    return bool(cfg.tunnel_token) or cfg.tunnel.lower() in ("quick", "on", "1", "true", "yes")


def start(cfg: Config) -> None:
    """Start the tunnel in the background (kept running, restarted if it drops)."""
    if not wanted(cfg):
        return
    if len(cfg.app_pin or "") < MIN_PIN:
        state["error"] = f"Not opened to the internet: set REEL_APP_PIN (at least {MIN_PIN} characters) first."
        print(f"  {state['error']}")
        return
    exe = cloudflared()
    if not exe:
        state["error"] = ("cloudflared isn't installed. Windows: winget install --id Cloudflare.cloudflared  "
                          "(then restart the app). Mac: brew install cloudflared.")
        print(f"  {state['error']}")
        return
    threading.Thread(target=_keep_running, args=(cfg, exe), daemon=True).start()


def _keep_running(cfg: Config, exe: str) -> None:
    named = bool(cfg.tunnel_token)
    # http2 (TCP 443-style traffic on port 7844) gets through more firewalls than the default QUIC (UDP).
    base = [exe, "tunnel", "--no-autoupdate", "--protocol", "http2"]
    cmd = base + (["run", "--token", cfg.tunnel_token] if named else ["--url", f"http://localhost:{cfg.port}"])
    wait = 5
    while True:
        started = time.time()
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
            for line in proc.stdout:
                if named and "Registered tunnel connection" in line and cfg.public_url and state["url"] != cfg.public_url:
                    _announce(cfg, cfg.public_url)
                found = None if named else QUICK_URL.search(line)
                if found and found.group(0) != state["url"]:
                    _announce(cfg, found.group(0))
            proc.wait()
        except OSError as exc:
            state["error"] = f"cloudflared couldn't start: {exc}"
            log.error(state["error"])
        state["url"] = ""
        # A tunnel that ran a while restarts at once; one that keeps failing backs off up to 5 minutes.
        wait = 5 if time.time() - started > 300 else min(300, wait * 2)
        log.warning("The internet link dropped; reconnecting in %d s", wait)
        time.sleep(wait)


def _announce(cfg: Config, url: str) -> None:
    state.update(url=url, error="")
    print(f"\n  From anywhere:     {url}   (PIN required)\n")
    try:
        (cfg.output_dir / "public_url.txt").write_text(url + "\n", encoding="utf-8")
    except OSError:
        pass
    if cfg.telegram_bot_token and cfg.telegram_chat_id:
        import requests

        try:
            requests.post(f"https://api.telegram.org/bot{cfg.telegram_bot_token}/sendMessage",
                          data={"chat_id": cfg.telegram_chat_id,
                                "text": f"🔗 Reel Studio is open at {url}\n(PIN required. A new link each time the app starts.)"},
                          timeout=20)
        except requests.RequestException as exc:
            log.warning("Couldn't send the link on Telegram: %s", exc)
