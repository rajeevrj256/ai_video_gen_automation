"""Channel rules: what every new low-poly video does so that more of the people YouTube shows it to keep watching,
and more of those who watch subscribe. Rules for the writer's prompt (`block`), fixes made in code (`tidy`), checks
that send a storyboard back once (`check`, `enforce`), the post's title, description and hashtags (`post_issues`,
`retitle`), and what a finished video did about each rule (`card`, in its report).

Where the rules come from (the user: "understand my channel ... more views and that viewer should convert to
subscriber ... do some rule so every video follow"): the user's channel as exported on 13 Nov 2026, eight days after
its first Short: 10 public Shorts with 6,351 views and 18 subscribers, 4 long films with 16 views.

- THE FIRST SECONDS. YouTube counts a Short's view when it starts to play, but its watch time per view is far below
  its average view duration (the dinosaur Short: 375 minutes over 1,335 views is 17 s a view, against an average view
  of 30 s), so the average is over the viewers who stayed: an estimated 46-71% per Short, 56% across them all (the
  API's own `engagedViews` gives the exact figure; youtube.py reads it now). More than four in ten of the people
  shown a Short swiped it away at once. Every low-poly Short faded in from black.
- SECONDS 5 TO 10. Every retention curve is flat for 4-5 s and has its steepest second between 4.4 s and 8 s: by
  second 10 a quarter to a half of the viewers who stayed have gone (59-83% left at 8 s). The one Short that lost
  the fewest (97% at 8 s) is a run of bigger and bigger feats from its first shot. YouTube's own comparison with
  videos of the same length puts the opening quarter of every other Short at 0.17-0.40 (0.5 is typical) and most
  closing quarters at 0.44-0.74: the people who stay like the endings; the second beat loses them. The fiction
  writer's own rule sent the story back to 'THREE DAYS EARLIER' and his ordinary life at exactly that moment.
- THE LAST SECOND. 44% -> 12% and 17% -> 7.5% in the final second: the hold and fade to black the timeline put on
  every video. Nobody stays for a fade, so nobody sees the Short start again.
- SUBSCRIBERS. 2.8 per 1,000 views. Most per view: the chase with one hero (6 from 955 views) and the cast intro
  that asks for it and promises a film (4 from 1,181); the one-off what-ifs 1.4-1.6 per 1,000.
- COMMENTS. 8 on the Short that ends on a question with two sides ('a hero, or a monster?'), 0-2 on every other.
- TITLES. The one-word ones (PACKED, WATCHING, TOMORROW, DISCIPLINE) have 0-72 views each; the titles that ask the
  video's question 226-1,335.

Ten videos and one week are thin. These are the best reading of the numbers, not proof: the audit's 'still watching
at 10 s' and 'stayed to watch' say after the next ten videos whether each rule earned its place.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from . import hooks

log = logging.getLogger(__name__)

VERSION = 1
HERO = "Ethan"  # his name in every video (the cast intro's card, the user's own descriptions)
END_TAG = "Subscribe for the next one"  # the small tag over a Short's last seconds ('' = none)
END_TAG_MAX = 44
OPENING_SHOTS = 5  # the shots that carry seconds 0-12
OPENING_WORDS = 8  # the most words a line there has (the prompt); a line over OPENING_OVER sends the storyboard back
OPENING_OVER = 10
OPENING_PAUSE = 0.5  # the longest pause after a line there (slow motion: SLOW_PAUSE)
PAUSE = 1.0  # ...and anywhere else in a Short
SLOW_PAUSE = 2.0
TITLE_MAX = 60  # characters the prompt asks for; over TITLE_OVER the title is written again
TITLE_OVER = 72
TITLE_WORDS = 4  # fewer words than this is a label, not a title
HASHTAGS = 3  # besides '#shorts'
REVISE_MOST = 90  # shots: a longer storyboard (a film written act by act) is never sent back whole
WPS = 2.7  # words a second, to guess a line's length before it is recorded
STILL = {"stand", "sit", "sit-floor", "lie", "lie-side", "think", "look-out", "read", "nod", "sigh"}  # nothing moves
REWIND = re.compile(r"\b(earlier|ago|before|previously|flashback|hours? back|days? back)\b", re.I)
BOILERPLATE = re.compile(r"\s*[|:\-–—]+\s*(an?\s+)?(3d\s+|low[- ]poly\s+)?animat(ed|ion)\s+(short\s+)?(film|flim|short|story|movie)\s*$", re.I)
HASHTAG = re.compile(r"#+[\w]+", re.UNICODE)

SHORT_OPENING = """
CHANNEL RULES FOR A SHORT (from this channel's own YouTube numbers; where anything above disagrees, these win):
THE FIRST 10 SECONDS. Four in ten of the people YouTube shows a Short to swipe it away in the first second or two, and \
of those who stay, a quarter to a half leave between second 5 and second 10. So:
- Shot 1 is {shot1} Something moves in its very first frame. Its line (8 words at most, or none) says the \
impossible thing or what is at stake, and starts at once: no stamp on shot 1. Never an establishing shot, a title, \
someone waking up, walking in, sitting or standing still.
- NO REWIND: the story runs forward from shot 1. Never a stamp or line like '... EARLIER', '... AGO' or 'BEFORE', \
never a flashback, never a calm stretch of his ordinary life after the opening. What the viewer has to know arrives \
inside the action, in a few words.
- Shots 2 to 5 (seconds 3-12) each bring something NEW and bigger than the shot before it: a new event, place, \
threat or reveal. Never a second look at the same thing, never an explanation. Each of the first five shots is under \
3 seconds: a line of 8 words at most, `pause` 0 (slow motion aside).
- One question carries the whole Short: raised in the first 3 seconds, answered only in the last 5.
ALL THE WAY THROUGH:
- Something changes on screen every 3 seconds at most. A shot with no line gets a `pause` of 1 at most (slow motion \
2). Leave out every shot the story works without: a Short that ends early beats one that drags.
"""
SHOT1 = {"fiction": "the story already happening at its most striking moment (not a moment borrowed from later: the "
                    "story starts there and goes on).",
         "life": "the struggle itself in one picture (the alarm ringing and his hand not moving; shoes on, still "
                 "inside), not the calm before it."}

SHORT_ENDING = {
    "fiction": """THE LAST 5 SECONDS:
- The answer or the twist lands in the last two or three shots. The final line then asks the viewer one question \
they can answer in a few words by taking a side ('Hero, or monster?', 'Would you open it?'), set `red`.
- THE LOOP: the last shot is in the place, light and framing of shot 1 (or on the same object or pose), so the Short \
starts again without a seam. Nothing comes after the question: no goodbye, no moral, no 'the end'.
""",
    "life": """THE LAST 5 SECONDS:
- The ending line in `red` as above (a quiet sting or a small win), never a moral.
- THE LOOP: the last shot is in the place, light and framing of shot 1 (or on the same object or pose), so the Short \
starts again without a seam. Nothing comes after the ending line.
"""}

FILM = """
CHANNEL RULES FOR A FILM (from this channel's own YouTube numbers; where anything above disagrees, these win):
- The first 30 seconds decide who stays: open on the film's most striking moment and the question the film answers, \
before any title, morning routine or slow walk. No shot longer than 4 seconds in the first 30, and the first line is \
8 words at most.
- A new turn (a reveal, a danger, a new place, a change in what he wants) every 30-40 seconds; leave out what the \
story works without.
- The ending answers the opening's question and leaves the viewer with one question of their own.
"""

FOLLOW = {
    "fiction": """A CHANNEL PEOPLE COME BACK TO:
- He is the same man in every video and he has a name: {hero} (unless the brief names him otherwise). Someone says \
it once in the first half ('{hero}!'), and the description uses it.
- Nobody asks for a subscribe, a like or a comment in the spoken words: the editor shows a small tag at the end.
""",
    "life": """A CHANNEL PEOPLE COME BACK TO:
- He is the same man in every video. The narration stays 'he'; the description may call him {hero}.
- Nobody asks for a subscribe, a like or a comment in the spoken words: the editor shows a small tag at the end.
"""}

POST = """THE POST (search and the channel page read these, and they decide who taps a film):
- youtube_title: 5 to 10 words, 60 characters at most: the question or the impossible event itself in plain words, \
its strongest word early ('What If You Could Stop Time?', 'The Police Couldn't Catch Him'). Never one or two words, \
never the film's own poetic title by itself, never '| An Animated Short Film' or the like, no hashtags, not all \
capitals, one emoji at most.
- description: sentence 1 says the hook in other words (it shows in search); then one or two sentences of what \
happens, without the ending; then one question for the comments. No hashtags, no 'subscribe'.
- hashtags: exactly 3, the most specific first: the subject ('#whatif', '#timetravel', '#carchase'), then \
'#animation'. (The app adds '#shorts' to a Short.)
- tags: 8 to 14 phrases people would type to find this video ('what if you could stop time', 'time stop', 'animated \
short film', 'low poly animation'), the specific ones first.
- comment_question: the one question to pin as the first comment: short, about the viewer, answerable in a few \
words ('What would you do with one frozen minute?').
"""


SILENT = """
CHANNEL RULES FOR A SILENT SCENE (from this channel's own YouTube numbers):
- The first frame is the scene itself, already in the moment, with something moving (his hands, a fork, a screen).
- One feeling, carried all the way: every shot moves it on (something new to see, a look, a change in his face).
- He is the same man in every video: Ethan.
"""


def block(*, short: bool, fiction: bool, script: bool = False, hero: str = HERO, silent: bool = False) -> str:
    """The channel's rules for a writer's prompt. A script the user wrote keeps its words and order: it only gets the
    rules for the post. A silent scene keeps its quiet: no question ending, no loop, no tag; its opening and its post."""
    kind = "fiction" if fiction else "life"
    if silent:
        return SILENT + POST
    if script:
        return "\n" + POST
    hero = (hero or HERO).strip() or HERO
    story = (SHORT_OPENING.format(shot1=SHOT1[kind]) + SHORT_ENDING[kind]) if short else FILM
    return story + FOLLOW[kind].format(hero=hero) + POST


def clean_tag(text: str) -> str:
    """'##Time Travel ' -> 'timetravel' (letters and digits only, no '#')."""
    return re.sub(r"[^\w]", "", str(text or ""), flags=re.UNICODE).replace("_", "").lower()


def hashtags(tags: list[str], short: bool, most: int = HASHTAGS) -> list[str]:
    """The post's hashtags as '#word', each once, the specific ones first, '#shorts' last on a Short."""
    out = []
    for t in tags or []:
        t = clean_tag(t)
        if t and t != "shorts" and t not in out:
            out.append(t)
    return [f"#{t}" for t in out[:most]] + (["#shorts"] if short else [])


def clean_title(title: str) -> tuple[str, list[str]]:
    """The title without hashtags and without an '| An Animated Short Film' tail, and the hashtags it carried."""
    found = [clean_tag(h) for h in HASHTAG.findall(title or "")]
    text = HASHTAG.sub(" ", title or "")
    for _ in range(2):
        text = BOILERPLATE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" |-–—:"), [h for h in found if h]


def title_issues(title: str) -> list[str]:
    words = re.findall(r"[^\W\d_]+['’]?[^\W\d_]*|\d[\d,.×x]*", title or "", flags=re.UNICODE)
    letters = [c for c in title if c.isalpha()]
    out = []
    if len(words) < TITLE_WORDS:
        out.append(f"the title '{title}' is only {len(words)} word{'s' if len(words) != 1 else ''}: it has to say the "
                   "question or the impossible event itself")
    if len(title) > TITLE_OVER:
        out.append(f"the title is {len(title)} characters; 60 at most")
    if len(letters) > 8 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        out.append("the title is in capitals; write it in normal title case")
    return out


def seconds_of(shot) -> float:
    """About how long a shot runs, before its line is recorded."""
    words = len((shot.line or "").split())
    return round((0.6 + words / WPS if words else 1.6) + float(shot.pause or 0), 2)


def _moves(shot) -> bool:
    """Something in the shot moves: a person doing more than standing or sitting, a big thing under way, an effect."""
    return (any(a.action not in STILL for a in shot.actors) or any(b.motion != "still" for b in shot.big) or bool(shot.fx)
            or shot.camera in ("crash-zoom", "orbit", "chase", "lead", "tracking", "pass-by", "heli"))


def tidy(story, *, short: bool, script: bool = False) -> list[str]:
    """What code can put right without Claude: the post's hashtags and title, and (a Short that isn't the user's own
    script) pauses that hold the opening or a silent shot too long. Returns what it changed."""
    notes = []
    title, carried = clean_title(story.youtube_title)
    if title and title != story.youtube_title.strip():
        notes.append(f"Title without hashtags or a boilerplate tail: '{title}' (was '{story.youtube_title.strip()}')")
        story.youtube_title = title
    tags = hashtags(list(story.hashtags) + carried, short)
    if tags != list(story.hashtags):
        story.hashtags = tags
    desc = re.sub(r"[ \t]+\n", "\n", HASHTAG.sub("", story.description or "")).strip()
    desc = re.sub(r"[ \t]{2,}", " ", desc)
    if desc != (story.description or "").strip():
        notes.append("Hashtags taken out of the description (the app adds them once)")
        story.description = desc
    if short and not script and not story.intro:
        cut = 0
        for i, s in enumerate(story.shots):
            most = SLOW_PAUSE if s.slowmo else OPENING_PAUSE if i < OPENING_SHOTS else PAUSE
            if s.pause > most + 1e-6:
                s.pause = most
                cut += 1
        if cut:
            notes.append(f"{cut} pause{'s' if cut != 1 else ''} shortened (opening {OPENING_PAUSE:g} s, later {PAUSE:g} s, "
                         f"slow motion {SLOW_PAUSE:g} s at most)")
        first = story.shots[0] if story.shots else None
        if first is not None and first.stamp.strip() and first.line.strip() and not REWIND.search(first.stamp):
            nxt = story.shots[1] if len(story.shots) > 1 else None
            if nxt is not None and not nxt.stamp.strip():
                nxt.stamp = first.stamp
                notes.append(f"The stamp '{first.stamp.strip()}' moved from shot 1 to shot 2: the first line starts at once")
            else:
                notes.append(f"The stamp '{first.stamp.strip()}' left off shot 1: the first line starts at once")
            first.stamp = ""
    return notes


def check(story, *, short: bool, script: bool = False) -> list[str]:
    """What breaks the channel's rules and only the writer can put right, each as an instruction. Nothing for the
    user's own script, a cast intro, or a storyboard too long to send back whole."""
    if script or story.intro or not story.shots or len(story.shots) > REVISE_MOST:
        return []
    out = []
    spoken = [(i, s) for i, s in enumerate(story.shots) if s.line.strip()]
    if spoken and hooks.weak(spoken[0][1].line):
        out.append(f"The first line (\"{spoken[0][1].line.strip()}\") opens with a generic phrase "
                   f"('{hooks.weak(spoken[0][1].line)}'): open on the impossible thing or the stake itself.")
    if not short:
        return out
    for i, s in enumerate(story.shots):
        text = s.stamp.strip() if REWIND.search(s.stamp) else s.line.strip() if len(s.line.split()) <= 5 and REWIND.search(s.line) else ""
        if text:
            out.append(f"Shot {i + 1} jumps back in time ('{text}'). A Short never rewinds: let the story start at shot 1 "
                       "and run forward. Take the rewind out with the ordinary-life shots after it, and put what the "
                       "viewer must know into the action in a few words.")
            break
    first = story.shots[0]
    if not _moves(first):
        out.append("Shot 1 has nothing moving (" + (", ".join(f"{a.who} {a.action}" for a in first.actors) or "nobody in it")
                   + "): open on the story's most striking moment, with an action already under way.")
    long = [f"shot {i + 1} ({len(s.line.split())} words)" for i, s in enumerate(story.shots[:OPENING_SHOTS])
            if len(s.line.split()) > OPENING_OVER]
    if long:
        out.append(f"The opening is slow: {', '.join(long)}. Each of the first {OPENING_SHOTS} shots has a line of "
                   f"{OPENING_WORDS} words at most, and each brings a new, bigger event.")
    if story.kind == "fiction" and spoken and not spoken[-1][1].line.strip().rstrip("\"'”’ ").endswith("?"):
        out.append(f"The last line (\"{spoken[-1][1].line.strip()}\") isn't a question: end on one question the viewer can "
                   "answer in a few words by taking a side, set `red`.")
    return out


class Post(BaseModel):
    youtube_title: str = Field(description="5-10 words, 60 characters at most")
    description: str
    comment_question: str


def retitle(cfg, story, problems: list[str], *, short: bool, hero: str = HERO, ask_fn=None) -> bool:
    """One small call: a title (and with it the description and the comment question) that follows the rules for the
    post. False, with the story left as it was, when it can't be had."""
    from .llm import ask

    system = ("You write the YouTube post for a short animated film: its title, description and the question to pin "
              "as the first comment. You get what happens in it and what is wrong with the title now.\n\n"
              + POST + f"\nHis name is {hero}. Use only what happens in the film; never promise what it doesn't show.")
    lines = " / ".join(s.line.strip() for s in story.shots if s.line.strip())[:1800]
    prompt = (f"The film: '{story.title}': {story.problem}\nIts lines: {lines}\nThe description now: {story.description}\n"
              f"The title now: {story.youtube_title}\nWhat is wrong: {'; '.join(problems)}.\nWrite the three again.")
    try:
        call = ask_fn or (lambda sy, pr: ask(cfg.ai_backend, cfg.claude_model, sy, pr, Post, allow_web=False, effort="low", timeout=600))
        new = call(system, prompt)
    except Exception as exc:  # noqa: BLE001 - a plain title is better than no video
        from .stopper import Paused
        if isinstance(exc, Paused):
            raise
        log.warning("Couldn't write the title again: %s", exc)
        return False
    title, _ = clean_title(new.youtube_title)
    if not title or title_issues(title):
        return False
    story.youtube_title = title
    story.description = HASHTAG.sub("", new.description or story.description).strip()
    story.comment_question = (new.comment_question or story.comment_question).strip()
    return True


INSTRUCTION = ("The storyboard breaks the channel's rules (CHANNEL RULES above). Put these right and change nothing else "
               "that the rules don't ask for; keep the story, the people and the length:\n")


def enforce(cfg, story, *, short: bool, seconds: int, minutes: float, script: bool = False, hero: str = HERO,
            progress=log.info, revise=None):
    """The story as the channel's rules want it: tidied in code, sent back to the writer once if it still breaks a
    rule only the writer can fix (kept as it was if the second version is no better), its title written again if
    it is a label. What was done is left on the story (`growth`), for the report."""
    notes = tidy(story, short=short, script=script)
    issues = check(story, short=short, script=script)
    left = issues
    if issues:
        progress(f"Channel rules: {len(issues)} thing{'s' if len(issues) != 1 else ''} only the writer can put right; sending the storyboard back once")
        for x in issues:
            progress("Channel rules: - " + x.split(": ")[0].split(". ")[0][:160])
        try:
            if revise is None:
                from .lowpoly import story as S

                def revise(st, text):
                    return S.revise(cfg, st, text, short=short, seconds=seconds, minutes=minutes)
            new = revise(story, INSTRUCTION + "\n".join(f"- {x}" for x in issues))
            notes2 = tidy(new, short=short, script=script)
            left2 = check(new, short=short, script=script)
            if len(left2) < len(issues):
                story, left, notes = new, left2, notes + notes2
                progress("Channel rules: the new storyboard follows them" if not left2 else
                         f"Channel rules: {len(issues) - len(left2)} of {len(issues)} put right")
            else:
                progress("Channel rules: the second storyboard was no better; keeping the first")
        except Exception as exc:  # noqa: BLE001 - the first storyboard still makes a video
            from .stopper import Paused
            if isinstance(exc, Paused):
                raise
            log.warning("Channel rules: couldn't send the storyboard back: %s", exc)
    problems = title_issues(story.youtube_title)
    if problems:
        was = story.youtube_title
        if retitle(cfg, story, problems, short=short, hero=hero):
            notes.append(f"Title written again: '{story.youtube_title}' (was '{was}')")
            problems = []
    for n in notes:
        progress("Channel rules: " + n)
    story.growth = {"version": VERSION, "fixed": notes, "sent_back": issues, "left": left + [p[0].upper() + p[1:] + "." for p in problems]}
    return story


def card(story, *, short: bool, end_tag: str = "", loop: bool = False) -> dict:
    """What this video does about each rule, for its report and its page."""
    g = dict(getattr(story, "growth", None) or {})
    shots = story.shots
    spoken = [s.line.strip() for s in shots if s.line.strip()]
    t, opening = 0.0, []
    for s in shots[:OPENING_SHOTS]:
        opening.append({"at": round(t, 1), "line": s.line.strip(), "seconds": seconds_of(s)})
        t += seconds_of(s)
    left = check(story, short=short) if g else []
    return {"version": g.get("version", VERSION), "on": bool(g), "first_line": spoken[0] if spoken else "",
            "last_line": spoken[-1] if spoken else "", "opening": opening, "opening_seconds": round(t, 1),
            "loop": bool(loop), "loops_to_start": bool(shots) and shots[0].set == shots[-1].set, "end_tag": end_tag,
            "comment": getattr(story, "comment_question", "") or "", "title_characters": len(story.youtube_title),
            "fixed": g.get("fixed", []), "sent_back": g.get("sent_back", []), "left": left + [x for x in g.get("left", []) if x not in left and "title" in x.lower()]}


def end_tag(text: str | None) -> str:
    """The tag as shown: one short line, no hashtags or links."""
    t = re.sub(r"\s+", " ", HASHTAG.sub("", str(text or ""))).strip()
    t = re.sub(r"https?://\S+", "", t).strip()
    return t[:END_TAG_MAX].rstrip()


def main(argv: list[str] | None = None) -> int:
    """`python -m reelgen.growth <video folder or story.json>`: a storyboard read against the channel rules."""
    import sys
    from pathlib import Path

    from .lowpoly import story as S

    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("usage: python -m reelgen.growth <video folder or story.json>")
        return 2
    path = Path(args[0])
    path = path / "story.json" if path.is_dir() else path
    story = S.load(path)
    short = not any(a == "--film" for a in args[1:])
    c = card(story, short=short)
    print(f"{story.youtube_title} ({c['title_characters']} characters)")
    print(f"Opens on: {c['first_line']!r}; the first {len(c['opening'])} shots take about {c['opening_seconds']} s")
    for o in c["opening"]:
        print(f"  {o['at']:>5.1f} s  {o['line'] or '(no line)'}")
    print(f"Ends on: {c['last_line']!r}; back where it started: {'yes' if c['loops_to_start'] else 'no'}")
    print(f"Pinned comment: {c['comment'] or '(none)'}")
    found = check(story, short=short) + [p[0].upper() + p[1:] + "." for p in title_issues(clean_title(story.youtube_title)[0])]
    print("Follows the channel rules." if not found else "Breaks the channel rules:\n" + "\n".join(f"- {x}" for x in found))
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
