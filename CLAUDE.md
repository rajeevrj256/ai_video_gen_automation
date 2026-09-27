# Context for Claude Code sessions

This repo holds two video tools for 9:16 short-form video. Read `README.md` for the
user-facing overview. This file covers what a new session needs in order to work
fast on the user's own machine, and the traps that have already cost time.

- `ai-reels-generator/`: **Reel Studio** (Python + a Remotion editor). Fully automatic
  trend → script → fact-check → voice → footage → Remotion edit → verify pipeline,
  with a local web app. Its own README has the details.
- `remotion-studio/`: **Remotion Studio**, hand-built motion graphics, imported from
  `rajeevrj256/remotion_claude_generation`. It has its own `CLAUDE.md` with traps
  specific to it (named `Layer` instead of `AbsoluteFill`, the canvas editor, the
  OneDrive patches). Follow that file when working in that folder.
- `calculator/`: the repo's original React calculator, unrelated. Leave it alone.

Working branch: `claude/ai-auto-generate-reels-shorts-muhsa4` (GitHub repo
`rajeevrj256/ai_video_gen_automation`, formerly `calculator`).

## Commands

```bash
./start-all.sh                      # or start-all.bat: Reel Studio + Remotion Studio + layout server
cd ai-reels-generator
./start.sh                          # Reel Studio only (first run creates .venv, npm installs remotion/)
.venv/bin/python -m reelgen --count 1 [--topic "..."]     # Windows: .venv\Scripts\python
cd remotion && npx tsc --noEmit     # typecheck the reels editor
npx remotion still src/index.ts Reel out.png --frame=60   # render one frame of the demo props
cd ../../remotion-studio && npm run studio / npm run typecheck
```

## How Reel Studio works (ai-reels-generator/reelgen/)

| File | Role |
|---|---|
| `pipeline.py` | The loop: write → `check_script` → `fact_check_script` (fixes up to 2×, no attempt used) → voice → footage → render → `check_video` → `review_with_claude`. Up to `REEL_MAX_ATTEMPTS` tries; the best attempt is kept. |
| `script_writer.py` | `system_prompt(style)`: shared rules + a block per `video_style` (`facts` true stories, fact-checked; `story` fiction; `comedy` jokes; `mix` rotates them per video in `pipeline.run`). Fact-check runs only for `facts`; the review rubric and post text adapt per style. `ReelScript` schema (`hook_question`, `answer`, scenes, `visual_queries`, `graphic`). Every video is one story around one question: a hook of 12 words or fewer (question, hidden origin, contradiction...), scenes linked by but/so, the answer only at the end. Topic rules, AI-cliché ban list, stock-footage query rules. |
| `llm.py` | Claude via the logged-in `claude -p --json-schema` CLI (no API key) or the Anthropic API. Model `claude-opus-5-5` at effort `high` by default (`CLAUDE_MODEL`, `REEL_CLAUDE_EFFORT`, or Settings). Not `CLAUDE_EFFORT`: Claude Code sessions set that name themselves. |
| `verify.py` | Script checks, fact-check (web search), ffmpeg checks (≤30s, audio, black frames, captions), Claude review of a 6-frame contact sheet. |
| `voice.py` | edge-tts (online, exact word timings) with Kokoro fallback (offline ONNX, estimated timings). The whole narration is spoken in **one take** at a steady `REEL_VOICE_RATE` and cut into per-scene WAVs; per-scene synthesis made every scene end on the same falling tone and sounded like reading. Default voice `en-US-AndrewMultilingualNeural`. |
| `visuals.py` | Pexels search. Keeps only results whose page slug shares a word with the query. |
| `video.py` | Builds props and runs `remotion render` in `ai-reels-generator/remotion/`; falls back to moviepy. `plan_transitions` keeps Claude's per-scene transition (flash/zoom/slide/glitch/fade) but forbids repeats and forces 2+ kinds. |
| `sfx.py` | Synthesised sounds, one per transition (whoosh, impact, swish, glitch, shimmer) plus a pop for graphics. No audio files. |
| `longform.py` | **Long videos** (8-10 min, 16:9, fully animated, no footage): `LongScript` (chapters of beats, each a narration line + an animated visual), `check_long_script`, `fact_check_long` (fixes before recording), one voice take per chapter (`long_voice`, default `en-IN-PrabhatNeural`, `long_language` Indian English), Remotion composition `Long` (`remotion/src/long/`), review on 2 frames per chapter, YouTube chapter timestamps in the description. Jobs with `length: "long"` go to `run_long_batch`. |
| `categories.py` | Library categories. New scripts carry `category` (Claude picks from `CATEGORIES`); older reports get a keyword guess (`categorize`), plurals only. The Videos page shows one shelf per category with search and filters; a video's category can be changed on its page. |
| `runlog.py` | Run history in `<output>/run_history.json`: every finished job (manual, automation, resume) with Claude tokens per video and per step; the History tab reads it. Token metering lives in `llm.py` (`start_meter`, one record per Claude call from Claude Code's `modelUsage`); the pipeline sends records as hidden `§usage` progress lines (`§done`, `§skip` too), and each report stores `usage`. |
| Pause/resume | Every step boundary saves `checkpoint.json` and calls `pause_point()`; Pause sets `job['pause']`, the video stops after its current step, and Resume continues from the checkpoint (videos that never started are made fresh). |
| `rerender.py` | Re-make a finished video with another voice and/or subtitles on/off (video page, job `rerender`): same script and graphics; Shorts re-download the same clips from `footage.json` (links saved by `visuals.pexels_video`), older videos search again. No Claude calls. A Short that runs past 29 s is re-voiced 6% faster (up to twice). |
| Subtitles | `captions` (Settings, Create page, automations, per job): off sends no caption layer; long-video visuals then move to the centre and grow ~10%. |
| `automations.py` | Several scheduled automations in `<output>/automations.json` (name, time, days, count, style, length, topic, `last_run`), run by `server.scheduler`; the old single `schedule_time` becomes the first one. |
| `server.py`, `web/` | Local app, job queue, automations API, PIN. |

The reels editor is `ai-reels-generator/remotion/` (Remotion **4.0.529**, pinned; the
Studio project uses `^4.0.0`, so keep versions separate). Props shape: `src/types.ts`.

## Using this machine's CPU and GPU

Set these in `ai-reels-generator/.env`. They're read by `video.py`:
- `REEL_CONCURRENCY=<cores>`: parallel frame rendering, the biggest speed win.
- `REEL_PARALLEL=2` (Settings: "Videos made at the same time"): this many videos run at once
  across all jobs (a shared semaphore in `pipeline.run`; every job gets its own thread in `server.py`). Claude and download waits overlap; renders still queue on a
  semaphore of `REEL_PARALLEL_RENDERS` (default 1), because two renders fight for the same cores.
  Batch log lines are tagged `[V<n>] `; the app splits them into one row per video.
- `REEL_GL=angle` (Windows) / `egl` (Linux): GPU for the headless browser. If renders
  come out black or crash, remove it.
- `REEL_HWACCEL=if-possible`: NVENC encoding on NVIDIA GPUs. On machines without a
  usable NVIDIA GPU, Remotion fails instead of falling back, so `video.py` retries once
  without it.
- Kokoro (offline voice) runs on CPU through onnxruntime. For GPU on Windows you could
  swap in `onnxruntime-directml`. Not done yet: measure first, since voice takes only a
  few seconds anyway.

Where the time goes (measured, 4-core cloud VM): Claude writing 1–1.6 min,
fact-check 1–5 min, voice + footage about 0.6 min, Remotion edit 2.6–3.1 min, Claude
review about 1 min. A failed review costs a whole extra try.

## Traps already hit

- **Remotion browser download**: `remotion.media` can be blocked on restricted networks.
  Set `REEL_CHROME=<path to chrome.exe or chromium>`, which adds
  `--browser-executable ... --chrome-mode=chrome-for-testing`.
- **OneDrive on Windows**: every file there is a reparse point, so Remotion's bundler
  fails with EPERM symlink errors. `remotion/scripts/patch-remotion-windows.js` runs on
  `postinstall`. Rerun it after upgrading Remotion.
- **WinError 5 when finishing a video**: renaming `...-working` to its final name fails on Windows while any file
  inside is open (OneDrive syncing, antivirus). `fsutil.move` retries for ~30 s, then copies. Keeping the project
  outside OneDrive (or `REEL_OUTPUT_DIR` outside it) avoids the locks entirely.
- **Microsoft voice 403**: `speech.platform.bing.com` refuses some cloud IPs. Auto mode
  falls back to Kokoro (the model downloads once, about 350 MB, into `assets/models/`).
- **edge-tts ignores system CAs**: `voice.py` swaps its SSL context for
  `SSL_CERT_FILE` when that's set (for TLS-inspecting proxies).
- **Stock footage can't show named people, specific artifacts or rare animals.** That
  was the #1 review failure. The writer is told to avoid such topics and to query
  close-ups; the reviewer accepts theme-appropriate footage. Pexels reads "football"
  as American football, so use "soccer".
- **Rendered files are big** (CRF 18: 25–45 MB for 30s). Fine for Instagram/YouTube,
  over Telegram's 50 MB bot limit only rarely.
- **Claude usage limits**: a batch can run out of Claude Code usage ("You've hit your session
  limit · resets 10:30pm (UTC)"). `llm.ask` reads the reset time, pauses every video thread at
  its current step until then (+2 min), and retries that same call, so nothing is redone. The
  app shows "Paused till HH:MM". The time zone may be `Asia/Calcutta`, which needs `tzdata`.
  If the app is closed during the pause, the job is lost.
- **`.env` holds keys** (Pexels, optional Anthropic/Telegram). Never print, commit or
  paste it. It's git-ignored.

## The user's standing preferences

- **Accuracy over speed.** Never invent or "adjust" a figure. Graphics numbers must
  match the narration and real sources. No politics or rumours about real people.
- **Videos must not look AI-made:** creator voice, no AI clichés (list in
  `script_writer.py`), real footage, varied pacing.
- **Max 30 seconds**, faster voice.
- **Verify, don't assert.** After changing the editor, render a still and look at it;
  after pipeline changes, make one real video and read its `report.json`.
- **Only one session should edit a branch at a time.** Fetch before you push, and never
  force-push over someone else's commits.
