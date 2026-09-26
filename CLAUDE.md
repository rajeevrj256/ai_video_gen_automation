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
| `script_writer.py` | Claude prompt + `ReelScript` schema (scenes, `visual_queries`, `graphic`). Topic rules, AI-cliché ban list, stock-footage query rules. |
| `llm.py` | Claude via the logged-in `claude -p --json-schema` CLI (no API key) or the Anthropic API. |
| `verify.py` | Script checks, fact-check (web search), ffmpeg checks (≤30s, audio, black frames, captions), Claude review of a 6-frame contact sheet. |
| `voice.py` | edge-tts (online, exact word timings) with Kokoro fallback (offline ONNX, estimated timings). |
| `visuals.py` | Pexels search. Keeps only results whose page slug shares a word with the query. |
| `video.py` | Builds props and runs `remotion render` in `ai-reels-generator/remotion/`; falls back to moviepy. `plan_transitions` keeps Claude's per-scene transition (flash/zoom/slide/glitch/fade) but forbids repeats and forces 2+ kinds. |
| `sfx.py` | Synthesised sounds, one per transition (whoosh, impact, swish, glitch, shimmer) plus a pop for graphics. No audio files. |
| `server.py`, `web/` | Local app, job queue, daily schedule, PIN. |

The reels editor is `ai-reels-generator/remotion/` (Remotion **4.0.529**, pinned; the
Studio project uses `^4.0.0`, so keep versions separate). Props shape: `src/types.ts`.

## Using this machine's CPU and GPU

Set these in `ai-reels-generator/.env`. They're read by `video.py`:
- `REEL_CONCURRENCY=<cores>`: parallel frame rendering, the biggest speed win.
- `REEL_PARALLEL=2` (Settings: "Videos made at the same time"): a batch runs this many videos
  in threads (`pipeline.run`). Claude and download waits overlap; renders still queue on a
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
