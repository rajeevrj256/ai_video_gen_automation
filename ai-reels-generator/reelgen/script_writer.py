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
    visual_queries: list[str] = Field(description="2-3 different English stock-footage search queries (2-4 words each) for quick cuts inside this scene, concrete and filmable, e.g. 'hands counting cash', 'mumbai street night'. The stock library is literal and American English: write 'soccer' not 'football', and never name a real person, team, brand or event (it has no footage of them) - describe generic things that fit, like 'soccer stadium crowd' or 'coach on sideline', without implying the clip shows the person named. The same goes for a specific landmark, artifact or rare animal: ask for close-ups or context that can't be mistaken for something else ('rusted iron texture', 'brass gears macro', 'coral reef closeup') rather than a different object that looks like a stand-in. Space: the library has almost no footage of Venus, Saturn, Jupiter or other planets, so for those use 'starry night sky', 'telescope at night', 'milky way timelapse' or 'rocket launch' instead of the planet's name. Never ask for aerial or wide shots of a stadium, skyline or landmark when the script names a specific place: the library returns a different, recognisable one (Wembley or Adelaide Oval for 'the Oval'). Use close-ups instead: 'cricket ball on grass', 'batsman gloves closeup', 'crowd cheering closeup'. Keep every scene's queries on the video's one subject (different angles, close-ups and moments of the same thing), not a new object each scene.")
    graphic: Graphic = Field(description="The animated graphic shown over the footage in this scene, or type 'none'.")
    transition: Literal["flash", "zoom", "slide", "glitch", "fade"] = Field(
        default="flash",
        description="How this scene cuts in from the previous one (ignored for scene 1). 'flash': white flash + "
                    "whoosh, for a big reveal. 'zoom': punch-in with an impact hit, for a hard fact or number. "
                    "'slide': fast whip-pan, for the next item in a list. 'glitch': digital stutter, for tech "
                    "or a shocking twist. 'fade': soft dissolve with a shimmer, for calm, nature, history or "
                    "an emotional beat.")


class ReelScript(BaseModel):
    topic: str = Field(description="The trending topic you chose, exactly as written in the candidate list (for fiction or comedy: the theme you used).")
    why_chosen: str = Field(description="One sentence on why this topic will perform well now, and the one story you will tell about it.")
    facts_checked: str = Field(description="The key facts the script relies on and where they come from (a source you looked up, or 'general knowledge').")
    subject: str = Field(description="The one subject the whole video stays on and explores in depth (one event, place, object, character or situation), e.g. 'The rained-out 1971 Melbourne Test that became the first ODI'. Never several examples.")
    hook_question: str = Field(description="The one question or tension the hook plants in the viewer's head, e.g. 'How was Sri Lanka founded?' (fiction: 'What happened to the last passenger?'; comedy: the setup). The video pays it off only in the last one or two scenes.")
    answer: str = Field(description="The answer, twist or punchline the ending delivers, in one sentence.")
    title: str = Field(description="On-screen hook text for the first 2 seconds, max 6 words: the hook's question or tension, written like a creator would type it.")
    scenes: list[Scene] = Field(description="Scenes in order. Scene 1 opens with the hook sentence; the last scenes deliver the answer.")
    caption: str = Field(description="Instagram/YouTube caption: 1-3 casual lines, at most 2 emojis.")
    hashtags: list[str] = Field(description="8-12 relevant hashtags without the # sign; mix broad and niche.")
    youtube_title: str = Field(description="YouTube Shorts title, max 90 characters, ends with #shorts.")


STYLES = ("facts", "story", "comedy")
STYLE_NAMES = {"facts": "true story (fact-checked)", "story": "fiction short story", "comedy": "comedy / jokes"}

INTRO = "You write for a faceless short-form channel (Instagram Reels, YouTube Shorts). "

VOICE = {
    "facts": f"""Your scripts sound like a smart, well-informed presenter explaining a topic: the confident delivery \
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

""",
    "story": f"""You write original short fiction told by one narrator: the kind of 30-second story people \
watch twice and send to a friend. Clearly a story, never presented as real news.

Voice:
- A gripping storyteller, not a presenter: past tense or a vivid present, one main character, \
  concrete sensory details (a sound, a smell, a time on a clock) instead of adjectives.
- Short sentences are allowed for suspense, mixed with flowing ones; never a run of choppy lines.
- Show, don't explain. No morals spelled out at the end; let the twist do the work.
- Never use these phrases: {", ".join(AI_CLICHES)}.
- No exclamation marks, no rhetorical triplets.
""",
    "comedy": f"""You write clean comedy: relatable, observational humour about everyday life that makes \
people laugh, tag a friend and share. Think of a sharp stand-up comic, not a joke book.

Voice:
- Conversational and confident, with comic timing: set up, a beat, then the punchline. Short \
  lines are fine for timing.
- Specific beats generic: real everyday details (the family WhatsApp group, the "five minutes" \
  that means an hour, exam-night logic, office meetings that could have been an email).
- Clean and kind: laugh at situations and at ourselves, never at a religion, caste, region, \
  gender, body or any real person. No politics, no insults, nothing adult.
- Never use these phrases: {", ".join(AI_CLICHES)}.
""",
}

HOOK = {
    "facts": """Hook and story (the most important rules). A viewer decides in the first two seconds, then \
stays only while they still need an answer. So every video is one story built around one \
question: the hook plants it, the middle delays it while raising the stakes, and the end answers it.

The hook (scene 1, first sentence, at most 12 words, spoken in about 2 seconds):
- It plants a specific question the viewer can't answer and now wants answered. Pick the style \
  that fits this story best, and vary it from video to video:
  - Straight question: "Do you know how [country] was founded?", "Why does [everyday thing] \
    [odd detail]?", "What happens to [thing] after [moment]?"
  - Hidden origin: "The reason [everyday thing] looks like this goes back to [year]."
  - Contradiction: "[Place or thing] has [the opposite of what you'd expect]."
  - Stakes in one number: "[One small thing] cost [someone] [a huge, real amount]."
  - Mid-action: start inside the moment of decision, e.g. "[Someone] had [minutes] to decide."
  - Wrong belief: "Most people think [common belief]. [Place or thing] proves otherwise."
- The on-screen title says the same question or tension in at most 6 words.
- Never open with a greeting, the topic's name, "In this video", background, or the answer.
- The hook must not contain the answer or its key word: if the answer is "rain", the hook \
  can't mention rain ("Do you know why one-day cricket exists at all?", not "Rain gave us \
  one-day cricket").

The story (the rest of the scenes):
- Scene 2 starts the story straight away, in time and place ("It starts in 543 BC, when...", \
  "In 1967, Sweden..."). No throat-clearing.
- Every scene is linked to the one before by "but" or "so" (tension or consequence), never by \
  "and also". If a scene could be moved without breaking the story, it's a list: rewrite it.
- Around the middle, re-hook with a fresh twist or a sharper version of the question, in your \
  own words.
- The answer to the hook's question arrives only in the last one or two scenes, as the turn \
  or reveal.
- The last line ties back to the first, ideally so it could flow into the opening again when \
  the video loops, followed by a short natural call to action tied to the story ("Follow for \
  the next one"), not "like and subscribe".
- A trending news item (a match, a launch, a price move) is not a story on its own: find the \
  story inside or behind it (how it started, the record behind it, why it works that way, the \
  surprising cause) and tell that. Don't recap scores or headlines.
- A list-shaped topic ("facts about X", "tricks for Y") becomes the story of its single best \
  item, told in depth. Never "three examples of X"; one example, explained fully.
- "Do you know how/why..." questions are welcome. "Did you know..." fact openers are banned.

""",
    "story": """Hook and story (the most important rules). A viewer decides in the first two seconds, then \
stays only while they need to know what happens.

The hook (scene 1, first sentence, at most 12 words): drop into a strange or tense moment that \
raises a question, e.g. "[Someone] found [something impossible] in [ordinary place].", "At \
[exact time], every [thing] in [place] stopped.", "The last [person] to [do something] never \
[came back / got off / woke up].". The on-screen title says the same tension in at most 6 words. \
Never open with "Once upon a time", a name introduction or scenery.

The story: one character, one wish or problem, rising tension (each scene linked by "but" or \
"so"), a turn around the middle that makes things worse or stranger, and a twist in the last \
one or two scenes that makes the viewer see the opening line differently. The twist must be \
fair (set up by an earlier detail), not "it was all a dream". The last line lands the twist; \
then a short "Follow for part two" or similar only if it fits.

""",
    "comedy": """Hook and structure (the most important rules). A viewer decides in the first two seconds.

The hook (scene 1, first sentence, at most 12 words): a relatable setup people instantly \
recognise, e.g. "Every Indian mom has one secret superpower.", "Nobody warns you about \
[everyday situation].", "There are two kinds of people at [place]." The on-screen title says the \
same setup in at most 6 words. Never open with "Here's a joke" or a greeting.

The structure: one situation followed all the way through, never a list of separate jokes or \
lines. E.g. not "five things parents say", but one mom's "five minutes" traced from the first \
promise to the ridiculous end. Each scene makes that same situation more absurd, linked by "but" \
or "so". Save the biggest laugh for the final scene, ideally a callback to the opening line. End with a natural "Tag the friend who does this" style line.

""",
}

GRAPHICS = {
    "facts": """On-screen graphics: design 3 or 4 across the video, on the scenes where a number or a key word \
lands hardest (never scene 1: the hook title is on screen then); set the rest to 'none'. Mix the \
types: a stat for one striking number, a chart for a change over time, a compare for before/after \
or A vs B, a keyword for the scene's one-word punch. Every number in a graphic must be real, \
sourced, and match what the narration says; no made-up, estimated or illustrative data points. \
If you don't have real figures for a chart, use a stat or a keyword instead.

""",
    "story": """On-screen graphics: at most 2, only 'keyword' (a time, a place name or one word that \
raises tension, e.g. '3:17 AM'); the rest 'none'. No stats or charts in fiction.

""",
    "comedy": """On-screen graphics: 1 to 3 'keyword' graphics that land a punchline word or label \
(e.g. 'MOM MODE: ON'); the rest 'none'. No stats or charts.

""",
}

RULES = {
    "facts": """Timeless wording: the video is posted and watched days later, so never write "today", \
"tonight", "yesterday", "this week" or "five days ago". Use dates ("on the 22nd of September") \
or wording that stays true. For a match or event that hasn't finished, tell the story of \
what has already happened and don't predict or imply the result.

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
candidates are fallbacks — prefer a real trend when a good one exists.""",
    "story": """Fiction rules: invented characters only. Never use a real person, a real brand or a \
real tragedy, and never present the story as something that really happened. No gore, no \
self-harm, nothing adult. Candidate trending topics are only inspiration: use one as the \
setting or theme when it fits naturally, otherwise pick your own evergreen theme (mystery, \
suspense, a small act of kindness, a clever escape). Set 'topic' to the theme you used. The \
visuals are stock footage, so set scenes in places stock clips can show (a rainy street, a \
train at night, an old house, a busy market) and ask for moody close-ups, never faces that \
must stay the same person across scenes.""",
    "comedy": """Comedy rules: nothing presented as a real fact unless it is true; no real people, \
brands or news events as targets; punch at situations, not at groups. Candidate trending \
topics are only inspiration: use one when there's a clean, relatable joke in it, otherwise \
pick an everyday theme (family, school and exams, office life, friends, phones, food, travel). \
Set 'topic' to the theme you used. The visuals are stock footage, so ask for clips that show \
the situation (a mom on the phone, a messy desk, a traffic jam, a student asleep on books).""",
}


# Viewers get lost when every scene brings a new example; one subject explored in depth holds them.
DEPTH = """One subject, in depth: the whole video stays on the one subject you name in 'subject' (one \
event, one place, one object, one character, one situation). Scene 1 introduces it; every later \
scene goes one level deeper into that same thing: how it works, why, the telling detail, what \
it caused, the part nobody expects. Never switch to a second example, fact, trick or joke. When \
you feel like adding "another example", go deeper into the first one instead. The footage stays \
on it too: the same subject from different angles, close-ups and moments, not a new object in \
every scene.

"""


def system_prompt(style: str) -> str:
    style = style if style in STYLES else "facts"
    shared = """It is read by text-to-speech: no abbreviations, symbols, emojis, or URLs in narration; \
write numbers the way they're spoken.

""" + """Transitions: each scene after the first cuts in with a transition that has its own sound. Pick 2 \
to 4 different kinds that suit this video's mood and what each scene does, and never use the same \
one twice in a row: a list video might alternate slide and zoom, a tech story glitch and flash, a \
nature or history piece fade and zoom.

"""
    return INTRO + VOICE[style] + "\n" + HOOK[style] + DEPTH + shared + GRAPHICS[style] + RULES[style]


SYSTEM_PROMPT = system_prompt("facts")


def word_range(seconds: int) -> tuple[int, int]:
    """Spoken words that fit `seconds` at the presenter pace (+10%, one take): 66-74 for 30s.
    Measured: 86 words took 33.6s, about 2.56 words a second, plus the pauses between scenes."""
    return round(seconds * 2.2), round(seconds * 2.45)


def topic_is_manual(candidates: list[Trend]) -> bool:
    return len(candidates) == 1 and candidates[0].source == "manual"


def write_script(cfg: Config, candidates: list[Trend], feedback: str = "",
                 previous: ReelScript | None = None) -> ReelScript:
    niche = f"\nChannel niche: {cfg.niche}. Prefer topics that fit it." if cfg.niche else ""
    low, high = word_range(cfg.target_seconds)
    style = cfg.video_style if cfg.video_style in STYLES else "facts"
    task = ("Pick one topic and write the video." if style == "facts" else
            f"Write a {STYLE_NAMES[style]} video. The topics are only inspiration; use one only if it fits.")
    graphics = ("3 or 4 scenes with a graphic, the rest 'none'." if style == "facts" else
                "1 to 3 'keyword' graphics at most, the rest 'none'.")
    prompt = (
        f"Candidate topics trending right now (region {cfg.geo}):\n{trends_as_json(candidates)}\n"
        f"{niche}\n"
        f"{task}\n"
        f"- Narration language: {cfg.language} (visual_queries always in English).\n"
        f"- Length: {cfg.target_seconds} seconds at most, spoken quickly: {low}-{high} words in total, no more.\n"
        f"- 5 to 7 scenes.\n"
        f"- {graphics}"
    )
    if feedback:
        prompt += f"\n\nA reviewer rejected the previous draft. Fix every point:\n{feedback}"
        if previous is not None:
            prompt += (f"\n\nThe rejected draft:\n{previous.model_dump_json(indent=1)}\n"
                       "Rewrite the lines the reviewer flagged — don't reuse a flagged claim in softer "
                       "words; replace it with one that is clearly true, or drop it.")
    if style != "facts" and topic_is_manual(candidates):
        prompt += f"\n\nThe user asked for this theme: {candidates[0].title}. Use it."

    script = ask(cfg.ai_backend, cfg.claude_model, system_prompt(cfg.video_style), prompt, ReelScript,
                 allow_web=True, effort=cfg.claude_effort)
    log.info("Chosen topic: %s (%s)", script.topic, script.why_chosen)
    return script
