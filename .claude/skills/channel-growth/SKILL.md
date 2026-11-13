---
name: channel-growth
description: The FrameBits channel's rules for videos that hold viewers and turn them into subscribers. Use when making a new Short or film (low-poly, Sticky or any pipeline), writing or changing a writer's prompt, writing a title, description, hashtags or pinned comment, reading the channel's YouTube numbers, or when the user asks why a video got few views or subscribers.
---

# Channel growth rules

The rules live in code: `ai-reels-generator/reelgen/growth.py`. Its docstring holds the evidence, `block()` the
rules every low-poly writer gets, `tidy()` and `check()` what is enforced. Read that file first; this page says how
to use it. Never restate a figure from memory: take it from the docstring or from a fresh export.

## Where the rules come from

The user's own channel, exported 13 Nov 2026 (10 Shorts, 6,351 views, 18 subscribers in eight days). Ten videos is
thin: every rule is a reading of those numbers, to be checked against the next ten, not a law.

| What the numbers showed | The rule |
|---|---|
| More than four in ten starts are swiped away at once (estimated) | Frame 1 is the picture, with something moving. No fade from black, no title, no stamp on shot 1 |
| Every Short loses a quarter to a half of its viewers between second 5 and second 10 | No rewind ('THREE DAYS EARLIER'), no ordinary-life stretch. Shots 2-5 each bring a new, bigger event, under 3 s each |
| The last second loses most of who is left (the fade) | No fade out. The last shot is back where shot 1 is, so the Short loops |
| 8 comments on the one Short that ends on a two-sided question, 0-2 elsewhere | Fiction ends on a question the viewer answers by taking a side; a question to pin as first comment |
| Most subscribers per view: one hero in a chase; a cast intro that asks | Same man (Ethan), named once. A small subscribe tag over the last seconds. Never a spoken ask |
| One-word titles: 0-72 views. Question titles: 226-1,335 | Title = the question or the impossible event, 5-10 words, 60 characters, no hashtags in it |

## Making a video

1. Low-poly tab with **📈 Channel rules** ticked (the default) does all of it. Leave it on.
2. A Short: one idea, 35-50 s (the best-held Short is 49 s and the 80 s one is the worst held; two data points, so
   a guide, not a rule). If the brief needs a rewind to make sense, rewrite the brief.
3. After writing, read the storyboard against the rules:
   `cd ai-reels-generator && .venv/bin/python -m reelgen.growth <video folder or story.json>` (add `--film` for a
   film). It prints the first five shots with their times and anything that breaks a rule.
4. On the video's page: copy **Pin this as the first comment**, post it from the channel, pin it.
5. Upload from the page (it goes up as Film & Animation with three hashtags and `#shorts`).
6. A film: make a Short from its best 45 s and set the film as that Short's Related video in YouTube Studio.

## Changing a writer or adding a pipeline

- Put a new rule in `growth.py` (prompt text in `block`, a code fix in `tidy`, a send-back in `check`), with the
  number that justifies it in the docstring. A rule with no number behind it doesn't go in.
- A code fix beats a prompt rule; a prompt rule beats a send-back (one send-back costs a whole storyboard).
- The user's own script keeps its words and order: only the post's rules apply (`script=True`).
- Another pipeline (Sticky, Stick, Shorts+): call `growth.block(...)` in its writer and `growth.tidy(...)` on its
  post. Check the pipeline's own first frame and last second on its timeline: a fade at either end breaks the rules.
- Run `.venv/bin/python -m reelgen.selfcheck` (it has `channel_rules`), then write one real storyboard and read it.

## Measuring whether a rule worked

YouTube tab → Refresh the numbers → Audit, or ⬇ For another AI. Compare videos made after the rules with the ones
before, on these, in this order:

1. **Stayed past the first seconds** (first frame and first words).
2. **Kept from second 5 to second 10** (the second beat).
3. **Average viewed %** and **still watching at the end** (the whole Short, the loop).
4. **Subscribers per 1,000 views**, **comments** (the ending, the tag, the pinned question).

Wait for at least five new Shorts with a few hundred views each before judging. If a number didn't move, change the
rule in `growth.py` and note why in its docstring. YouTube's numbers lag two to three days.

## What the rules never do

- Promise a video that doesn't exist ('Part 2 tomorrow') or a schedule the user hasn't set.
- Bend a fact, add clickbait the video doesn't deliver, or ask for a subscribe in the spoken words.
- Touch the words of a script the user wrote.
