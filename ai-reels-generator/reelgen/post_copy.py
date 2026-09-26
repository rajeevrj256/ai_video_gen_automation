"""Ready-to-paste post text for Instagram and YouTube Shorts, written after the video
is final: caption, title, description, tags and hashtags that are actually in use now
(Claude checks them with web search) rather than generic guesses."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from .config import Config
from .llm import ask
from .script_writer import ReelScript

log = logging.getLogger(__name__)


class PostCopy(BaseModel):
    instagram_caption: str = Field(description="Instagram caption without hashtags: a hook first line that makes people tap 'more', 1-2 short lines of value from the video, then a question that invites comments. At most 3 emojis. Plain, human tone.")
    instagram_hashtags: list[str] = Field(description="10-15 hashtags without '#', all relevant to this video: about 3 broad high-volume, 5-7 mid-size topic tags, 3-5 niche or local ones (e.g. city, language, community). Prefer tags you confirmed are actively used right now for this topic.")
    youtube_title: str = Field(description="YouTube Shorts title, max 70 characters, main search keyword near the start, curiosity without false clickbait. No hashtags.")
    youtube_description: str = Field(description="2-3 sentences that naturally include the main keywords people search for this topic, then a one-line call to subscribe. No hashtags here.")
    youtube_hashtags: list[str] = Field(description="3-5 hashtags without '#' for the end of the description, most important first (YouTube shows the first 3 above the title); include 'shorts'.")
    youtube_tags: list[str] = Field(description="10-15 search keywords/phrases for YouTube's Tags field, most specific first, no '#'.")
    hashtag_notes: str = Field(description="One sentence: where the trending hashtags came from (what you searched) or 'not verified' if you couldn't check.")


SYSTEM = """You are a social media manager for a faceless Reels/Shorts channel. You write the \
text that goes with a finished video so it gets found and watched: search-friendly titles and \
descriptions, a caption that earns comments, and hashtags that are really in use for this topic \
right now. Use web search to check current hashtags and search terms for the topic and region. \
Never promise anything the video doesn't deliver, and keep the facts identical to the script."""


def write_post_copy(script: ReelScript, cfg: Config) -> PostCopy:
    narration = " ".join(s.narration for s in script.scenes)
    prompt = (
        f"Topic: {script.topic}\nRegion: {cfg.geo}, language: {cfg.language}\n"
        f"On-screen hook: {script.title}\nVoiceover: {narration}\n"
        f"Draft caption: {script.caption}\nDraft hashtags: {', '.join(script.hashtags)}\n\n"
        "Write the Instagram and YouTube Shorts post text for this video."
    )
    return ask(cfg.ai_backend, cfg.claude_model, SYSTEM, prompt, PostCopy, allow_web=True)


def clean_tags(tags: list[str]) -> list[str]:
    seen, out = set(), []
    for t in tags:
        t = t.strip().lstrip("#").replace(" ", "")
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def post_text(report: dict) -> str:
    """The contents of post.txt: everything to paste when uploading."""
    ig_tags = " ".join(f"#{h}" for h in report.get("hashtags", []))
    yt_tags = " ".join(f"#{h}" for h in report.get("youtube_hashtags", []))
    return (
        "=== INSTAGRAM REELS ===\n"
        f"{report.get('caption', '')}\n\n{ig_tags}\n\n"
        "=== YOUTUBE SHORTS ===\n"
        f"Title:\n{report.get('youtube_title', '')}\n\n"
        f"Description:\n{report.get('youtube_description', '')}\n\n{yt_tags}\n\n"
        f"Tags (paste into YouTube's Tags field):\n{', '.join(report.get('youtube_tags', []))}\n"
    )


def apply_post_copy(report: dict, script: ReelScript, cfg: Config, folder: Path) -> dict:
    """Write the post text for a finished video into its report and post.txt."""
    post = write_post_copy(script, cfg)
    report.update({
        "caption": post.instagram_caption,
        "hashtags": clean_tags(post.instagram_hashtags),
        "youtube_title": post.youtube_title,
        "youtube_description": post.youtube_description,
        "youtube_hashtags": clean_tags(post.youtube_hashtags),
        "youtube_tags": [t.strip().lstrip("#") for t in post.youtube_tags if t.strip()],
        "hashtag_notes": post.hashtag_notes,
    })
    report.pop("post_text_error", None)
    save_post_text(report, folder)
    return report


def save_post_text(report: dict, folder: Path) -> Path:
    path = folder / "post.txt"
    path.write_text(post_text(report), encoding="utf-8")
    return path
