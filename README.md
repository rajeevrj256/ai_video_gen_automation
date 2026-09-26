# AI Video Gen Automation

Two tools for short vertical videos (Instagram Reels, YouTube Shorts), in one repo:

| Folder | What it does | Opens at |
|---|---|---|
| [`ai-reels-generator/`](ai-reels-generator/) | **Reel Studio**: fully automatic. It picks today's trending topic, Claude writes and fact-checks a 30-second script, then it adds a voiceover and stock footage, edits with animated graphics (Remotion), and reviews the finished video. A phone-friendly web app shows you the results. | http://localhost:8765 |
| [`remotion-studio/`](remotion-studio/) | **Remotion Studio**: hand-built motion-graphics videos in React (e.g. the fact-checked UPI MDR explainer), with a drag-and-drop canvas editor, colour grades and exports for every platform shape. | http://localhost:3000 |

Reel Studio's editor (`ai-reels-generator/remotion/`) uses the same motion language as Remotion Studio (spring entrances, eased exits, safe areas, film grain), so both produce videos that look like one channel.

`calculator/` is the repo's original React calculator project and is unrelated to the video tools.

## How Reel Studio makes a video

```
Google Trends ─► Claude picks a topic and writes the script (web search for facts)
             ─► Claude fact-checks every claim, fixes wrong lines (before anything is rendered)
             ─► Voice: Microsoft neural voice online, or Kokoro offline on your PC
             ─► Footage: Pexels stock clips that match each scene
             ─► Remotion edit: captions, hook card, count-ups, charts, comparisons, grain
             ─► Checks: 30s max, audio, black frames, captions; Claude reviews the frames
             ─► Saved in ai-reels-generator/output/, shown in the app (and Telegram if set)
```

A video that fails a check is rewritten and made again (up to 3 tries). If none passes, you still get the best one, marked "not verified" with the reasons.

## Set up on your PC (one time)

Install:
1. [Python 3.10+](https://www.python.org/downloads/) (on Windows tick **Add Python to PATH**)
2. [Node.js LTS](https://nodejs.org)
3. [Git](https://git-scm.com/downloads)
4. Claude Code. On Windows, run in PowerShell: `irm https://claude.ai/install.ps1 | iex`. Then open a **new** terminal, run `claude` once and log in. Reel Studio uses this login, so you need no API key.

Then, in PowerShell (Windows) or a terminal (Mac/Linux):

```bash
git clone -b claude/ai-auto-generate-reels-shorts-muhsa4 https://github.com/rajeevrj256/ai_video_gen_automation
cd ai_video_gen_automation
```

Create `ai-reels-generator/.env` from the example and add your keys:

```bash
# Windows
copy ai-reels-generator\.env.example ai-reels-generator\.env
notepad ai-reels-generator\.env
# Mac / Linux
cp ai-reels-generator/.env.example ai-reels-generator/.env
```

Set at least `PEXELS_API_KEY` (free at https://www.pexels.com/api/). For more speed on a strong PC, see [Speed](#speed) below.

## Run everything

- **Windows:** double-click **`start-all.bat`**, or in PowerShell type `.\start-all.bat` (PowerShell needs the `.\`). It opens one window each for Reel Studio, Remotion Studio and its layout server.
- **Mac / Linux:** `./start-all.sh`. Ctrl+C stops everything; logs go to `logs/`.

The first run installs everything, which takes a few minutes. After that:
- **Reel Studio:** http://localhost:8765. On your phone, use the address and QR code printed in its window (same Wi-Fi), then **Add to Home Screen**.
- **Remotion Studio:** http://localhost:3000.

To run only one of them:
- **Reel Studio:** `ai-reels-generator/start.bat` (or `start.sh`).
- **Remotion Studio:** `cd remotion-studio`, then `npm run studio` and `npm run layout-server`.

Reel Studio from the command line:

```bash
cd ai-reels-generator
.venv/Scripts/python -m reelgen --count 3            # Windows (.venv/bin/python on Mac/Linux)
.venv/Scripts/python -m reelgen --topic "UPI rules 2026"
```

## Speed

One video is about 8 minutes when it passes on the first try. The slow steps are Claude's writing and fact-checking (1–5 min) and the Remotion edit (about 3 min on 4 cores). On a strong PC, set these in `ai-reels-generator/.env`:

| Setting | What it does | Try |
|---|---|---|
| `REEL_CONCURRENCY` | Frames rendered in parallel | your CPU's core count, e.g. `8` or `12` |
| `REEL_GL` | Lets the renderer's browser use the GPU | `angle` on Windows, `egl` on Linux |
| `REEL_HWACCEL` | GPU video encoding (NVIDIA NVENC) | `if-possible` (falls back to CPU if it fails) |
| `REEL_PARALLEL` | Videos made at the same time in a batch (also in Settings). While one waits on Claude, another downloads or renders | `2`; `3` on a 16 GB+ PC |
| `REEL_PARALLEL_RENDERS` | How many of those may render at once | `1`; `2` on 16+ cores |
| `REEL_MAX_ATTEMPTS` | Rewrite-and-retry budget | `3` (default); `1` = fastest, more "not verified" |

The best topics pass on the first try and look most real: money, science, nature, tech, places and history. Breaking news about named people is the hardest, because stock footage can't show them.

## More

- Reel Studio details: [`ai-reels-generator/README.md`](ai-reels-generator/README.md)
- Remotion Studio details: [`remotion-studio/README.md`](remotion-studio/README.md)
- Context for Claude Code sessions: [`CLAUDE.md`](CLAUDE.md)
