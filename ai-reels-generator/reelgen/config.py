"""Runtime configuration, read from environment variables (or a local .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the project has no extra dependency for it."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0]  # allow trailing comments
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(PROJECT_ROOT / ".env")

# Hard limit on video length. Longer targets are clamped and verify.py fails
# any finished video over it.
MAX_SECONDS = 30


def _env(name: str, default: str = "") -> str:
    # Empty values (e.g. unset GitHub Actions variables) fall back to the default.
    return os.environ.get(name, "").strip() or default


@dataclass
class Config:
    # How to reach Claude: "auto" (Claude Code CLI if installed, else API),
    # "claude-code" (your logged-in Claude Code, no API key) or "api".
    ai_backend: str = field(default_factory=lambda: _env("REEL_AI_BACKEND", "auto"))
    # Empty = Claude Code's default model / claude-opus-5 on the API.
    claude_model: str = field(default_factory=lambda: _env("CLAUDE_MODEL"))

    # Stock footage (free key from https://www.pexels.com/api/). Optional:
    # without it the video uses animated gradient backgrounds.
    pexels_api_key: str = field(default_factory=lambda: _env("PEXELS_API_KEY"))

    # Where the "response" goes. Optional: without it the result is only
    # written to output/<run>/report.json and printed.
    telegram_bot_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env("TELEGRAM_CHAT_ID"))

    # Content settings.
    geo: str = field(default_factory=lambda: _env("REEL_GEO", "IN"))
    language: str = field(default_factory=lambda: _env("REEL_LANGUAGE", "English"))
    voice: str = field(default_factory=lambda: _env("REEL_VOICE", "en-US-AndrewNeural"))
    # "auto" (Microsoft online voice, offline Kokoro if that's refused), "edge" or "kokoro".
    tts_engine: str = field(default_factory=lambda: _env("REEL_TTS", "auto"))
    # Kokoro voice override, e.g. af_heart, am_michael, bm_george, hf_alpha. Empty = match REEL_VOICE.
    kokoro_voice: str = field(default_factory=lambda: _env("REEL_KOKORO_VOICE"))
    niche: str = field(default_factory=lambda: _env("REEL_NICHE"))
    target_seconds: int = field(default_factory=lambda: int(_env("REEL_SECONDS", str(MAX_SECONDS))))

    # Video settings (9:16 vertical, what Reels and Shorts expect).
    width: int = 1080
    height: int = 1920
    fps: int = 30

    # Automatic quality check: how many times to regenerate a video that fails it.
    max_attempts: int = field(default_factory=lambda: int(_env("REEL_MAX_ATTEMPTS", "3")))

    # Local app (python -m reelgen serve).
    port: int = field(default_factory=lambda: int(_env("REEL_PORT", "8765")))
    app_pin: str = field(default_factory=lambda: _env("REEL_APP_PIN"))
    # Daily auto-generation time in 24h local time, e.g. "08:30". Empty = off.
    schedule_time: str = field(default_factory=lambda: _env("REEL_SCHEDULE"))
    # How many videos the daily run makes (1-15).
    schedule_count: int = field(default_factory=lambda: int(_env("REEL_SCHEDULE_COUNT", "1")))

    output_dir: Path = field(default_factory=lambda: Path(_env("REEL_OUTPUT_DIR", str(PROJECT_ROOT / "output"))))
    music_dir: Path = PROJECT_ROOT / "assets" / "music"
    font_path: str = field(default_factory=lambda: _env("REEL_FONT"))

    def __setattr__(self, name, value):
        # Env, .env and settings saved from the app all pass through here.
        if name == "target_seconds":
            value = max(10, min(int(value), MAX_SECONDS))
        super().__setattr__(name, value)


# Settings a user can change from the app; saved next to the videos.
EDITABLE = ["geo", "language", "voice", "tts_engine", "niche", "target_seconds", "schedule_time", "schedule_count", "ai_backend", "claude_model"]


def settings_path(cfg: Config) -> Path:
    return cfg.output_dir / "settings.json"


def load_settings(cfg: Config) -> Config:
    """Apply settings saved from the app on top of env/.env values."""
    import json

    path = settings_path(cfg)
    if path.exists():
        for key, value in json.loads(path.read_text(encoding="utf-8")).items():
            if key in EDITABLE:
                setattr(cfg, key, type(getattr(cfg, key))(value))
    return cfg


def save_settings(cfg: Config, updates: dict) -> Config:
    import json

    for key, value in updates.items():
        if key in EDITABLE:
            setattr(cfg, key, type(getattr(cfg, key))(value))
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    settings_path(cfg).write_text(json.dumps({k: getattr(cfg, k) for k in EDITABLE}, indent=2), encoding="utf-8")
    return cfg
