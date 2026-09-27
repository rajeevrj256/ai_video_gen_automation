"""Scheduled automations: several daily jobs, each with its own time, days, number of
videos, style, length and optional topic (e.g. 9:00 five Shorts, 18:00 one long video).

Stored in <output>/automations.json. The old single schedule (schedule_time /
schedule_count in Settings) becomes the first automation the first time this runs.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .config import Config, load_settings

STYLES = ("facts", "story", "comedy", "mix")
_lock = threading.Lock()


class Automation(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Daily videos"
    enabled: bool = True
    time: str = "09:00"  # HH:MM, this computer's local time
    days: list[int] = Field(default_factory=lambda: list(range(7)))  # 0 = Monday ... 6 = Sunday
    count: int = 3
    style: str = "facts"
    length: str = "short"  # short | long
    topic: str = ""  # empty = trending
    captions: bool = True  # subtitles burned into the videos
    last_run: str = ""  # ISO date of the last run, so a restart doesn't run it twice

    def clean(self) -> "Automation":
        self.name = self.name.strip()[:60] or "Automation"
        try:
            self.time = datetime.strptime(self.time.strip(), "%H:%M").strftime("%H:%M")
        except ValueError:
            raise ValueError("Time must look like 09:30")
        self.days = sorted({d for d in self.days if 0 <= d <= 6}) or list(range(7))
        self.style = self.style if self.style in STYLES else "facts"
        self.length = "long" if self.length == "long" else "short"
        self.count = max(1, min(self.count, 5 if self.length == "long" else 15))
        self.topic = self.topic.strip()[:200]
        return self


def _path(cfg: Config) -> Path:
    return cfg.output_dir / "automations.json"


def load(cfg: Config) -> list[Automation]:
    path = _path(cfg)
    if path.exists():
        return [Automation(**a) for a in json.loads(path.read_text(encoding="utf-8"))]
    # First run: carry over the old single daily schedule, if one was set.
    settings = load_settings(Config())
    if settings.schedule_time:
        first = Automation(name="Daily videos", time=settings.schedule_time, count=settings.schedule_count,
                           style=settings.video_style).clean()
        save(cfg, [first])
        return [first]
    return []


def save(cfg: Config, items: list[Automation]) -> None:
    path = _path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([a.model_dump() for a in items], indent=2, ensure_ascii=False), encoding="utf-8")


def upsert(cfg: Config, item: Automation) -> Automation:
    item = item.clean()
    with _lock:
        items = load(cfg)
        old = next((a for a in items if a.id == item.id), None)
        if old:
            item.last_run = old.last_run
            items = [item if a.id == item.id else a for a in items]
        else:
            items.append(item)
        save(cfg, items)
    return item


def delete(cfg: Config, automation_id: str) -> None:
    with _lock:
        save(cfg, [a for a in load(cfg) if a.id != automation_id])


def due(cfg: Config, now: datetime) -> list[Automation]:
    """Automations whose time is now and that haven't run today; marks them as run."""
    today = now.date().isoformat()
    with _lock:
        items = load(cfg)
        ready = [a for a in items if a.enabled and a.time == now.strftime("%H:%M")
                 and now.weekday() in a.days and a.last_run != today]
        for a in ready:
            a.last_run = today
        if ready:
            save(cfg, items)
    return ready


def next_run(a: Automation, now: datetime) -> str:
    """Human text for when it runs next, e.g. 'Today 18:00' or 'Mon 09:00'."""
    if not a.enabled:
        return "Off"
    hour, minute = map(int, a.time.split(":"))
    for ahead in range(8):
        day = date.fromordinal(now.date().toordinal() + ahead)
        at = datetime(day.year, day.month, day.day, hour, minute)
        if day.weekday() in a.days and at > now and not (ahead == 0 and a.last_run == day.isoformat()):
            return ("Today " if ahead == 0 else "Tomorrow " if ahead == 1 else at.strftime("%a ")) + a.time
    return "Off"
