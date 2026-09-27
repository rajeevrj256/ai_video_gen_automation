"""Claude picks the best trending topic and writes a short-form video script
that sounds like a real creator talking, not an AI."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field

from .config import Config
from .llm import ask
from .trends import Trend, trends_as_json

log = logging.getLogger(__name__)

# Phrases that instantly mark a video as AI-made. The writer is told to avoid
# them and the verifier rejects scripts that still contain them.
AI_CLICHES = [
    "did you know", "let's dive in", "dive into", "delve", "in today's video", "in this video",
    "buckle up", "mind-blowing", "mind blowing", "game-changer", "game changer", "unlock the secrets",
    "the world of", "fascinating world", "embark on", "journey", "tapestry", "testament to",
    "whether you're", "stay tuned", "without further ado", "let that sink in", "here's the kicker",
    "but here's the thing", "in conclusion", "ever wondered", "have you ever wondered",
    "smash that like", "you won't believe",
]


class Point(BaseModel):
    label: str = Field(description="Short label: a year, date or name for a chart point, or the side name for a compare, e.g. '2019', 'Before', 'India'.")
    value: float = Field(description="The plain number used for plotting, e.g. 152670 or 4.2. Must be a real figure.")
    display: str = Field(description="How the value is written on screen, e.g. '₹1.5 lakh', '42%', '8B'.")


class Graphic(BaseModel):
    type: Literal["none", "stat", "chart", "compare", "keyword"] = Field(
        description="'stat': one big number that counts up. 'chart': a line chart of 3-6 points over time. "
                    "'compare': before/after or A vs B, exactly 2 points. 'keyword': a word or short phrase slammed "
                    "on screen. 'none': no graphic, just footage.")
    headline: str = Field(description="stat: the number exactly as shown, e.g. '₹1,52,670' or '42%'. chart: the overall change, e.g. '+38%'. compare: a short verdict, e.g. '3x more'. keyword: 1-3 words. none: empty.")
    label: str = Field(description="What the number or chart is, 2-6 words, e.g. 'UPI payments per month'. Empty for none.")
    points: list[Point] = Field(description="chart: 3-6 points in time order. compare: exactly 2 points. Empty for stat, keyword and none.")


class Scene(BaseModel):
    narration: str = Field(description="What the voiceover says in this scene: 1-2 spoken sentences that carry on from the previous scene. The scenes are read in one continuous take.")
    visual_queries: list[str] = Field(description="2-3 different English stock-footage search queries (2-4 words each) for quick cuts inside this scene, concrete and filmable, e.g. 'hands counting cash', 'mumbai street night'. The stock library is literal and American English: write 'soccer' not 'football', and never name a real person, team, brand or event (it has no footage of them) - describe generic things that fit, like 'soccer stadium crowd' or 'coach on sideline', without implying the clip shows the person named. The same goes for a specific landmark, artifact or rare animal: ask for close-ups or context that can't be mistaken for something else ('rusted iron texture', 'brass gears macro', 'coral reef closeup') rather than a different object that looks like a stand-in.")
    graphic: Graphic = Field(description="The animated graphic shown over the footage in this scene, or type 'none'.")
    transition: Literal["flash", "zoom", "slide", "glitch", "fade"] = Field(
        default="flash",
        description="How this scene cuts in from the previous one (ignored for scene 1). 'flash': white flash + "
                    "whoosh, for a big reveal. 'zoom': punch-in with an impact hit, for a hard fact or number. "
                    "'slide': fast whip-pan, for the next item in a list. 'glitch': digital stutter, for tech "
                    "or a shocking twist. 'fade': soft dissolve with a shimmer, for calm, nature, history or "
                    "an emotional beat.")


class ReelScript(BaseModel):
    topic: str = Field(description="The trending topic you chose, exactly as written in the candidate list.")
    why_chosen: str = Field(description="One sentence on why this topic will perform well now.")
    facts_checked: str = Field(description="The key facts the script relies on and where they come from (a source you looked up, or 'general knowledge').")
    title: str = Field(description="On-screen hook text for the first 2 seconds, max 6 words, written like a creator would type it.")
    scenes: list[Scene] = Field(description="Scenes in order. Scene 1 is the hook.")
    caption: str = Field(description="Instagram/YouTube caption: 1-3 casual lines, at most 2 emojis.")
    hashtags: list[str] = Field(description="8-12 relevant hashtags without the # sign; mix broad and niche.")
    youtube_title: str = Field(description="YouTube Shorts title, max 90 characters, ends with #shorts.")


SYSTEM_PROMPT = f"""You write for a faceless short-form channel (Instagram Reels, YouTube Shorts). \
Your scripts sound like a smart, well-informed presenter explaining a topic: the confident delivery \
of a top explainer channel or a business-news anchor who knows the subject cold. Never like a child \
reading facts off a card, never like an AI, never a slow documentary. Viewers stop scrolling in \
the first second and watch to the end because every line makes them understand something.

Voice:
- An expert explaining clearly to a smart adult: confident, precise, calm authority, a little wit.
- The narration is one connected explanation, not a list of separate facts. Each scene follows \
  from the one before, linked by cause and effect ("because", "which is why", "that's where", \
  "so", "and that matters because").
- Natural sentence length, mostly 10 to 20 words, with an occasional short line for emphasis. \
  Never a run of tiny, choppy sentences; that is what sounds like a kid reading aloud.
- Give every number context: compared with what, or why it matters to the viewer.
- Specific beats generic: real numbers, names, places, dates.
- A point of view: what's surprising, what most people get wrong, what it means for the viewer.
- Plain adult vocabulary with contractions. No filler ("okay so", "honestly", "guys"), no \
  exclamation marks, no hype words, no baby talk.
- Never use these phrases: {", ".join(AI_CLICHES)}.
- No lists of three adjectives, no rhetorical triplets, no "It's not just X, it's Y".

Structure:
- Scene 1 is the hook: a bold claim, a surprising number, or a sharp question — no greeting.
- Each next scene adds a new fact or twist; keep an open loop until near the end.
- Last scene pays it off, then a short natural call to action tied to the topic
  (e.g. "Follow if you want part two"), not "like and subscribe".

It is read by text-to-speech: no abbreviations, symbols, emojis, or URLs in narration; \
write numbers the way they're spoken.

On-screen graphics: design 3 or 4 across the video, on the scenes where a number or a key word \
lands hardest (never scene 1: the hook title is on screen then); set the rest to 'none'. Mix the \
types: a stat for one striking number, a chart for a change over time, a compare for before/after \
or A vs B, a keyword for the scene's one-word punch. Every number in a graphic must be real, \
sourced, and match what the narration says; no made-up, estimated or illustrative data points. \
If you don't have real figures for a chart, use a stat or a keyword instead.

Transitions: each scene after the first cuts in with a transition that has its own sound. Pick 2 \
to 4 different kinds that suit this video's mood and what each scene does, and never use the same \
one twice in a row: a list video might alternate slide and zoom, a tech story glitch and flash, a \
nature or history piece fade and zoom.

Accuracy: only state facts you are confident about or have looked up. If a trend is breaking \
news, check what actually happened first (use web search if you have it); if you can't confirm \
details, explain the background people are searching for instead of guessing.

Topic choice: pick the candidate with the broadest appeal that works as a 30 second video. \
Skip tragedies, deaths, violence, explicit content, politics and politicians, and rumours, \
allegations or gossip about real people — anything where a wrong detail could mislead viewers \
about a real person. Sports, science, tech, money, entertainment releases, weather and culture \
are good fits. The visuals are stock footage plus animated graphics, so prefer topics generic \
footage can show (a place, an activity, money, nature, technology) over a story that is only \
about one named person, whom no stock clip can show. Evergreen \
candidates are fallbacks — prefer a real trend when a good one exists."""


def word_range(seconds: int) -> tuple[int, int]:
    """Spoken words that fit `seconds` at the brisk voice pace: 70-80 for 30s."""
    return round(seconds * 7 / 3), round(seconds * 8 / 3)


def write_script(cfg: Config, candidates: list[Trend], feedback: str = "",
                 previous: ReelScript | None = None) -> ReelScript:
    niche = f"\nChannel niche: {cfg.niche}. Prefer topics that fit it." if cfg.niche else ""
    low, high = word_range(cfg.target_seconds)
    prompt = (
        f"Candidate topics trending right now (region {cfg.geo}):\n{trends_as_json(candidates)}\n"
        f"{niche}\n"
        f"Pick one topic and write the video.\n"
        f"- Narration language: {cfg.language} (visual_queries always in English).\n"
        f"- Length: {cfg.target_seconds} seconds at most, spoken quickly: {low}-{high} words in total, no more.\n"
        f"- 5 to 7 scenes.\n"
        f"- 3 or 4 scenes with a graphic, the rest 'none'."
    )
    if feedback:
        prompt += f"\n\nA reviewer rejected the previous draft. Fix every point:\n{feedback}"
        if previous is not None:
            prompt += (f"\n\nThe rejected draft:\n{previous.model_dump_json(indent=1)}\n"
                       "Rewrite the lines the reviewer flagged — don't reuse a flagged claim in softer "
                       "words; replace it with one that is clearly true, or drop it.")

    script = ask(cfg.ai_backend, cfg.claude_model, SYSTEM_PROMPT, prompt, ReelScript, allow_web=True)
    log.info("Chosen topic: %s (%s)", script.topic, script.why_chosen)
    return script
