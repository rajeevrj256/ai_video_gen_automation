# Reel Studio – AI Reels / Shorts Generator

Makes faceless **Instagram Reels** and **YouTube Shorts** (30 seconds at most) from what's trending today, checks each video automatically, and keeps everything on your own computer. You watch, copy captions, and save videos from your phone.

Each video goes through these steps:

1. **Find trends.** It pulls Google Trends for your country and Reddit r/popular, with fallback topics if both are unavailable. It never repeats a topic.
2. **Claude writes it.** Claude picks the best topic, looks up the facts on the web, and writes a script in a creator's voice: a strong hook, short spoken lines (about 70–80 words in 5–7 scenes), and none of the usual AI phrases ("did you know", "let's dive in", "mind-blowing", …). It also designs 3–4 animated graphics for the video (a big number, a line chart, a before/after comparison or a keyword), using only real figures.
3. **Voice.** Natural neural voices (English, Hindi and 70+ languages), at the brisk pace of a Shorts creator. The pace and pitch shift a little between scenes so it doesn't sound robotic. It uses Microsoft's free online voices, and switches automatically to **Kokoro**, an open-source voice that runs on your own computer, if Microsoft refuses the connection (it does for some networks and cloud servers). The offline model downloads once, about 350 MB.
4. **Footage.** Two or three different stock clips per scene from Pexels, cut every few seconds with editor-style punch-in zooms. No clip is used twice.
5. **Editing.** Made with [Remotion](https://www.remotion.dev): 1080×1920, the animated graphics, word-by-word captions that pop in with the spoken word in yellow, a hook title, a white flash at each scene change, a progress bar, soft sound effects and optional music. Without Node.js it falls back to a simpler edit with no graphics.
6. **Automatic verification** (see below). A video that fails is rewritten using the reviewer's notes and made again.
7. **Delivery.** The video shows up in the app on your phone and PC, with optional Telegram delivery.

## Automatic verification

Every video passes three checks before it counts as done:

| Check | What it looks at |
|---|---|
| Script | AI-sounding phrases, word count for the target length, scene count, symbols that TTS would read out, 2–5 well-formed graphics |
| Technical | 1080×1920 resolution, **30 seconds at most**, audio present and loud enough, black frames, captions covering the whole voiceover, file size |
| Claude review | Claude looks at frames from the **finished video** plus the script and scores how human it feels, the hook, how well the visuals match, and accuracy. Any factual error, contradiction or clickbait exaggeration is a blocking issue |

If a check fails, Claude rewrites the script using the feedback and the video is made again, up to `REEL_MAX_ATTEMPTS` times (default 3). If every attempt fails, you still get the best one, marked **"Check"** instead of **"✓"**, with the reasons listed.

## Run it on your computer (recommended)

The app runs on your PC or Mac. Videos are saved in `output/` on that computer. Your phone connects to it over the same Wi-Fi.

**1. Install once**
- [Python 3.10+](https://www.python.org/downloads/) (on Windows, tick "Add Python to PATH")
- [Claude Code](https://claude.com/claude-code). Open a terminal, run `claude` once and log in. The app then uses **your Claude Code login**, so no API key is needed.
- [Node.js LTS](https://nodejs.org) for the video editor (animated graphics). Optional: without it videos use a simpler edit.

**2. Start**
- Windows: double-click **`start.bat`**
- Mac / Linux: run **`./start.sh`**

The first start installs everything. Then it prints:

```
  Reel Studio is running
  On this computer:  http://localhost:8765
  On your phone:     http://192.168.1.23:8765   (same Wi-Fi)
  [QR code]
```

**3. Open it on both devices**
- **Computer:** open `http://localhost:8765`.
- **Phone:** scan the QR code, or type the phone address, while on the same Wi-Fi.
  - iPhone: in Safari tap **Share → Add to Home Screen**. It then opens full-screen like an app.
  - Android: in Chrome tap **⋮ → Add to Home screen**.

In the app:
- **Videos:** tap a video to watch it. You can **Save video**, **Copy caption** (caption and hashtags), and **Copy YouTube title**, and you can see why the topic was picked and which facts were used.
- **Create:** make a video now, from today's trends or your own topic, with live progress.
- **Settings:** country, language, voice, niche, length (up to 30 s), a **daily automatic video** time, and which AI to use.

> Set `REEL_APP_PIN=1234` (your own PIN) in `.env` so nobody else on your Wi-Fi can use the app.
> The computer has to be on (and `start` running) to make videos and to watch them from your phone.

### Optional keys (`.env`)
- `PEXELS_API_KEY`: free from https://www.pexels.com/api/. **Strongly recommended.** Without it, videos use plain gradient backgrounds.
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`: also get each finished video on Telegram.
- `REEL_TTS`: `auto` (default), `edge` (Microsoft online only) or `kokoro` (offline only). Also in the app's Settings.
- Music: put royalty-free `.mp3` files in `assets/music/`.

### Command line

```bash
python -m reelgen                        # 1 video now
python -m reelgen --count 3
python -m reelgen --topic "Chandrayaan 4"
python -m reelgen --language Hindi --voice hi-IN-MadhurNeural
python -m reelgen serve                  # the app (what start.bat/start.sh run)
```

Each video gets a folder in `output/` containing `reel.mp4`, `thumbnail.jpg`, `report.json` (caption, hashtags, verification result, which editor made it), `script.json` and `review_frames.jpg` (the frames Claude reviewed).

## YouTube thumbnails (with Gemini, no API key)

On a video's page, **Thumbnail → Design thumbnail**. Claude looks at the video and designs a
thumbnail that makes people stop scrolling: one bold subject from the video, 2-4 huge words taken
from it that pair with the YouTube title (the title carries the search keyword, the thumbnail the
curiosity), in the video's colours. You get a prompt for Gemini plus two other ideas to A/B test.

1. Open the Gemini app → **Images**, set the aspect ratio to 16:9 (9:16 for a Short), paste the prompt.
2. Download the picture you like and upload it on the video page.
3. Reel Studio adds the words in big outlined type (exact spelling; untick the box if Gemini
   already wrote them) and Claude checks it against the video: right subject, right words,
   readable at phone size, a click-worthiness score, and a better prompt if it falls short.

The result is saved as `thumbnail-youtube.jpg` (1280x720, under YouTube's 2 MB limit).

## Optional: run in the cloud with GitHub Actions

`.github/workflows/ai-reels.yml` (at the repo root) makes a video every day with no computer needed. It uses an API key instead of Claude Code. Add these under **Settings → Secrets and variables → Actions**: `ANTHROPIC_API_KEY` (required), plus optionally `PEXELS_API_KEY`, `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Videos appear under each run's **Artifacts**.

## Project layout

```
start.bat / start.sh   one-click start (installs on first run)
web/                   the phone + desktop app (installable web app)
reelgen/
  server.py         local app server, job queue, daily schedule
  llm.py            Claude via Claude Code CLI or API key
  trends.py         trending-topic sources + history of used topics
  script_writer.py  creator-style script + banned AI phrases
  verify.py         script, technical and Claude review checks
  voice.py          voiceover (Microsoft online / Kokoro offline) with word timings
  visuals.py        Pexels footage (multiple cuts per scene)
  captions.py       caption timing (and caption images for the simpler edit)
  video.py          timeline, then the Remotion render (moviepy if Node is missing)
  sfx.py            whoosh and pop sound effects, made on the fly
  notifier.py       Telegram + GitHub run summary
  pipeline.py       runs all steps with verify-and-retry
remotion/           the video edit (React + Remotion), rendered by video.py
  src/Reel.tsx      the "Reel" composition: layers, audio, sound effects
  src/Graphics.tsx  stat / chart / compare / keyword graphics
  src/Captions.tsx  word-by-word pop captions
  src/HookTitle.tsx the opening hook card
  src/Background.tsx footage cuts, punch-in zoom, scene-change flash
```

To preview or tweak the edit: `cd remotion && npm run studio` opens Remotion Studio with sample props (`src/demo.ts`). The Python pipeline renders with `remotion render src/index.ts Reel out.mp4 --props=props.json --public-dir=<video folder>`.

## Notes

- **Posting is up to you.** Save the video from the app and upload it in Instagram or YouTube. Auto-posting needs a YouTube API app or an Instagram Business account; it can be added later.
- **"Not AI-looking" has limits.** Stock footage, a natural script, and varied voice and pacing get close to a real faceless channel. For the most human result, record the voiceover yourself: replace `reel.mp4`'s voice, or ask for a "use my recording" option.
- **Always watch before posting.** Verification catches a lot, but trending news can be sensitive.
