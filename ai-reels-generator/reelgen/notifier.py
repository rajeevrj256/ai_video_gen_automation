"""Deliver the result: Telegram message with the video, and a GitHub Actions summary."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

log = logging.getLogger(__name__)

TELEGRAM_VIDEO_LIMIT = 50 * 1024 * 1024  # Bot API upload limit


def verification_line(report: dict) -> str:
    if report.get("verified"):
        return f"✅ Verified (score {report.get('score')}/10)"
    return "⚠️ Not verified — check before posting: " + "; ".join(report.get("issues", []))[:400]


def format_message(report: dict) -> str:
    from .post_copy import post_text

    return (
        f"🎬 New reel ready\n{verification_line(report)}\n\n"
        f"Topic: {report['topic']} ({report['topic_source']})\n"
        f"Why: {report['why_chosen']}\n"
        f"Length: {report['duration_seconds']}s\n\n"
        + post_text(report)
    )


def send_telegram(token: str, chat_id: str, report: dict) -> bool:
    base = f"https://api.telegram.org/bot{token}"
    text = format_message(report)
    video = Path(report["video"])
    try:
        if video.exists() and video.stat().st_size < TELEGRAM_VIDEO_LIMIT:
            with open(video, "rb") as fh:
                resp = requests.post(
                    f"{base}/sendVideo",
                    data={"chat_id": chat_id, "caption": text[:1024], "supports_streaming": "true"},
                    files={"video": (video.name, fh, "video/mp4")},
                    timeout=300,
                )
            resp.raise_for_status()
            if len(text) > 1024:  # captions are capped at 1024 chars; send the rest as text
                requests.post(f"{base}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=30)
        else:
            requests.post(f"{base}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=30).raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Telegram delivery failed: %s", str(exc).replace(token, "<bot token>"))
        return False


def send_text(token: str, chat_id: str, text: str) -> bool:
    """A plain message (failures, updates). Never raises: an alert must not break what it reports on."""
    if not (token and chat_id):
        return False
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat_id, "text": text[:4000]}, timeout=20).raise_for_status()
        return True
    except requests.RequestException as exc:
        log.error("Telegram message failed: %s", str(exc).replace(token, "<bot token>"))
        return False


def write_github_summary(report: dict) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    tags = " ".join(f"`#{h}`" for h in report["hashtags"])
    with open(summary, "a", encoding="utf-8") as fh:
        fh.write(
            f"## 🎬 {report['title']}\n\n"
            f"| | |\n|---|---|\n"
            f"| Check | {verification_line(report)} |\n"
            f"| Topic | {report['topic']} ({report['topic_source']}) |\n"
            f"| Why | {report['why_chosen']} |\n"
            f"| Length | {report['duration_seconds']}s |\n"
            f"| YouTube title | {report['youtube_title']} |\n\n"
            f"**Caption**\n\n{report['caption']}\n\n{tags}\n\n"
            f"Download the video from this run's **Artifacts** section.\n"
        )


def notify(report: dict, token: str, chat_id: str) -> None:
    write_github_summary(report)
    if token and chat_id:
        if send_telegram(token, chat_id, report):
            log.info("Sent to Telegram chat %s", chat_id)
    print("\n" + format_message(report) + f"\n\nVideo: {report['video']}\n")
