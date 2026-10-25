"""Visual templates for long, medium and Script Videos: how every beat is drawn.

'classic' is the motion-graphics look every video had (photo backdrops, coloured worlds, camera moves). 'briefing'
(remotion/src/long/brief/Brief.tsx) comes from about 20 frames of a news-explainer channel the user sent ("analyse
this template ... not copy entirely ... must be dynamic and Claude can think what to do while creating new videos").
What was taken is the design language, not the frames:
- a near-black page with a faint square grid, no photos; a header strip naming the chapter on the left and the source
  on the right (or the video and the beat count), so the viewer always knows where they are and where it comes from;
- condensed display capitals for headlines with one or two words in the accent colour, small tracked mono labels
  above things ('WHAT ACTUALLY HAPPENED'), outlined tags beside them, Inter for sentences;
- colour as meaning: green done/safe, red threat/wrong, blue information, the accent for what to look at;
- diagrams instead of slides: chains of boxes and arrows, progress nodes that light up, ticked checklists, a field of
  icons for a count, a terminal, a profile card with a status badge, a value on a scale, a strip of dates, a receipt;
- everything builds in the order the line says it, earlier parts stay, later ones wait dimmed; the page holds still.
Each video gets its own accent and paper tone from its seed, and Claude picks the layout per beat from the story's
own evidence, so two Briefing videos are never built the same way.
"""
from __future__ import annotations

TEMPLATES = {
    "classic": ("✨ Classic", "Colourful motion graphics over photos of each chapter's place, camera moves, the hook "
                "pictures. Every video so far."),
    "briefing": ("📰 Briefing", "A clean news-explainer page: dark grid, a header with the chapter and the source, big "
                 "condensed headlines with one coloured word, and diagrams that build as they are said (chains of "
                 "boxes, checklists, progress steps, icon fields, terminals, receipts, dates)."),
}
BRIEFING_TYPES = ("flow", "checklist", "grid", "terminal", "card", "scale", "dates", "receipt")
ITEMS = {"flow": (2, 5), "checklist": (2, 4), "terminal": (1, 7), "scale": (2, 4), "dates": (3, 7), "receipt": (2, 6),
         "grid": (1, 2)}


def chosen(cfg) -> str:
    t = (getattr(cfg, "visual_template", "") or "classic").strip()
    return t if t in TEMPLATES else "classic"


def on(cfg) -> bool:
    return chosen(cfg) == "briefing"


RULES = """The visual template is BRIEFING: a clean news-explainer page (dark grid, a header strip, condensed display \
capitals, small mono labels, slate cards). You design every beat as a diagram of this line's own evidence, the way a \
good explainer graphic desk would, never a slide that repeats the narration. Decide the layout from what the line is:
- a chain (who did what to whom, A leads to B leads to C): 'flow', items 2-5 boxes in order: label = a small \
description above the name (max 5 words, e.g. 'trusted supplier'), text = the name (1-3 words), tone 'bad' for the \
threat, 'warn' for what to watch, 'good' for the safe side, '' otherwise.
- what to do, or conditions met one by one: 'checklist', items 2-4: text = the action or fact (max 9 words), label = a \
small condition above it ('if it does'), tone 'good' ticked, 'bad' crossed out, '' an empty box still to do; \
headline = its heading, sub = a short subheading.
- a sequence of stages reached so far: 'steps' (drawn as nodes that light up with a check), items 2-5 with label = the \
stage (1-3 words), text = a tiny note under it or empty, tone 'bad' for a failed stage.
- a count you can see (a thousand robots, 1,200 websites, 24 words): 'grid', icons[0] = the thing (Lucide name), \
items[0]: label = what they are, value = how many to draw (2-120; when the real number is larger, a representative \
field), display = the real number as the script states it; items[1] (optional): label = what the marked ones are, \
value = how many to mark in the same proportion, display = their real number, tone 'bad' or 'good'.
- code, a command, a log, a file list: 'terminal', headline = the window title ('bash', 'server log'), items = lines \
(max 7): label = '$' for a command, '#' for a comment, '▸' for a list line or empty; text = the line; tone 'warn' \
highlights the key line, 'bad' red, 'good' green. Only text the script states or that plainly shows what it says.
- one organisation, product or role and its status: 'card', headline = the name, sub = what it is or what happened \
(max 12 words), tags[0] = the status badge (1-3 words, 'credential revoked'), tone 'good' / 'bad'.
- one value on a range (losses out of a range, a score): 'scale', items = [the range's start, the value(s) marked \
(1-2), the range's end], each with value and display; tone of the marked one 'bad' / 'good'. Only a range the script \
states or one that is plainly the axis (0 to a round number above the value).
- days or dates that matter: 'dates', items 3-7 consecutive days: label = weekday or month (small), text = the day \
number; tone 'bad' / 'warn' marks the day(s) the line is about; sub = what the mark means.
- money added up: 'receipt', items 2-6 rows (label, display), the last row the total; headline = what bill it is.
- and the classic types, redrawn in this style: stat (a number counted up with a mono label: kicker), compare (two \
cards with big figures), timeline (a track with marked moments: tone 'bad' draws a red diamond), chart, quote (a \
card with the speaker in mono), icons (outlined line icons; tone 'bad' crosses them out), title and keyword.
Every visual may also have: kicker = a small mono label above it (2-5 words, a frame for the beat: 'what actually \
happened', 'before · skilled people'), accent = the 1-2 words of the headline drawn in the accent colour (the word the \
line hinges on), tags = 0-3 short outlined tags (1-3 words each) beside a headline, tone = the beat's meaning colour. \
Headlines are short and punchy (max 6 words), never the narration written out. Vary the layouts: never the same type \
three beats in a row, and use diagrams (flow, checklist, steps, grid, terminal, card, scale, dates, receipt, compare, \
timeline, chart) for most beats. Keep 'footage', 'model3d', 'scene' and memes rare here (at most one per chapter). \
Give every chapter a 'source': the outlet(s) and date this chapter's facts come from as the header shows them \
('Reuters · 19 Oct 2026', 'PHP.net · NCSC · AWS'), only sources actually used for it (for a user's script: only what \
the script or its description names), else empty. Never invent a figure, a line of code, a date or a name for a \
diagram: every number and name on screen is in the line or the script."""


def rules() -> str:
    return RULES
