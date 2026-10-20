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

## Music, openings and sound (every pipeline, automatic)

- **New music for every video**: with the AI engine installed (Anim tab), every video, Short or long, gets its own
  AI-made track (ACE-Step) from its mood, energy and story, in a genre none of the last few videos used. Without the
  engine (or with Settings > Content > Music set to composed), a new track is composed for each video instead.
- **Openings**: every writer is told how to open in the first 3-5 seconds (the most surprising concrete thing, no
  "Did you know" / "In this video" / greeting) and how the last videos opened, so openings don't repeat; a generic
  opener is rewritten before recording.
- **Sound**: every narration is levelled to the same loudness, the music sits under the voice (quieter while it
  speaks, fuller in the pauses), and every finished video is mastered to -14 LUFS, the level YouTube and Instagram
  play at.
- **Speaking speed**: 30-second Shorts speak briskly (+10%); long, medium, Script and Shorts+ videos at a normal pace
  (Settings, and Speaking speed on the Script tab). English voices read numbers in English ("1 lakh" is "one lakh",
  never "ek lakh"). On a finished video's page, **Voice, speed & subtitles → Speaking speed** re-records only the voice
  at another speed and re-times the same edit to it: the slides, memes, pictures, footage and music stay as they are,
  nothing is generated again and no Claude tokens are used.
  **▶ Try it first** makes a 15-20 s demo of the story's first lines with the chosen speed, voice or subtitles
  (1-3 minutes) and plays it next to the same lines of the original, so you can compare speeds before re-making.
- **Hook styles** (long, medium and Script videos): the first 30 seconds decide if people stay, so hooks open at full
  energy from the first frame. Pick a style on the Create page, the Script tab or in Settings (▶ See an example plays
  a sample of each): ⚡ **Kinetic words** (every word slams onto the screen as it's spoken), 🎬 **Fast cuts** (bright
  pictures, a jump-cut zoom every half second, bold captions), 💥 **Big stakes** (the number or key words slam in
  giant and shake the frame), 🚫 **Myth buster** (the common belief, stamped MYTH, then the truth teased), 👉 **It's
  you** (the viewer's own moment, each line popping up like a phone notification), ⏪ **Ending first** (how it ends,
  then a VHS rewind back to the start), ✅ **Promise + list** (a striking fact, what you'll know by the end, the points
  ticking onto a checklist), 🎞 **Coming up** (a trailer of the video's own best moments), or 🎞 **Cinematic** (the
  slower documentary look below). Auto rotates the energetic ones, never one of the last three videos'. Every hook
  confirms the title's promise within about 10 seconds, and with memes on, every style gets its meme. The spoken
  words only appear on screen with subtitles on.
- **Shorts from your long videos**: on a long, medium or Script video's page, **✂️ Short from this video** lists the
  script by chapter. Tap the first and last line of a part, then choose **Explain this part** (Claude retells it as a
  Short that stands on its own, only with facts those lines state, reusing the video's own graphics; 30-90 s) or
  **Use these lines as they are**. The Short opens on a hook line and ends on a line sending viewers to the full
  video, with an end card showing its thumbnail, title and an arrow to the link. Paste the long video's YouTube link
  and it goes in the description; in YouTube Studio set the long video as the Short's *Related video*. The Short is a
  new video in your library; the long one stays as it is.
- **Re-create only the hook**: on a finished video's page, **🪝 Hook** makes a new hook in another style (Claude
  rewrites it from the video's own facts; a Script Video keeps your words) and plays it next to the current one.
  **Save as a new video** copies the video, puts the new hook first and joins the rest after it in a few minutes, with
  no re-edit. The original video stays as it is.
- **Cinematic hook** (long videos, Script Videos, animated videos): the opening is cut like a documentary trailer:
  each shot in its own colour grade (amber, red, black-and-white, fire, cold) under film grain and flicker, yellow
  labels typed onto the picture ("LONDON, 1928"), whips, VHS glitches, a photo flown in, paper torn across the frame,
  a split-second montage at the climax, a dark drone with deep booms on the big cuts, then the music stops for a breath
  of silence (a subscribe button clicked in the dark) and the story starts with a question. With the AI engine
  installed, the hook's shots are cinematic AI stills (Settings > Hook pictures), checked by Claude before use; without
  it, they are motion graphics. Shorts open on a deep boom under the first word.

## Memes and funny explaining (option)

**Memes & humour** (Settings > Content, or per video on the Create page for medium and long videos, the Script tab and
Shorts+ with the motion-graphics look): *Off* (told like a documentary), *Some* or *Lots*.

- **Some / Lots**: the writer explains like a sharp, funny friend: every concept gets an everyday example you have lived
  (a salary gone by the 10th, Netflix instead of studying, onion prices), a recurring everyday character can carry them,
  and the jokes never bend a fact (the fact-check still runs). No jokes about religion, caste, region, bodies, poverty,
  tragedies or real people.
- **Memes** land the idea: about one beat in 8 (*Some*) or in 4 (*Lots*) is a meme whose format is the shape of the
  idea: a sweating person between two red buttons for a trade-off, nope/yep for the smarter choice, the expanding brain,
  "this is fine" in a burning room, panik/kalm/panik, expectation vs reality, "Nobody: / Me:", stonks and not stonks,
  change my mind, the four-panel plan that backfires, two people pointing at each other, a starter pack, or a big
  reaction face (shocked, crying, laughing, side-eye, mind blown...) with top and bottom text. They are drawn fresh by
  the editor with cartoon people (one recurring character per video), with their own sounds (a record scratch, a
  cartoon boing, the sad trombone...), so nothing is copied from a meme picture, a film or a real person.
- **Your own memes**: Settings > Media library > Memes takes pictures, GIFs and short clips (GIFs and .mov are turned
  into .mp4). Name each by what it means ("crying-cat-sad", "side-eye-doubt") and set its licence; Claude uses one only
  where its name fits the line, with top and bottom text. Add only files you may use: film stills, TV clips and photos
  of real people can bring copyright claims.
- **Real memes from the internet** (Settings > Meme pictures > Real memes from imgflip.com): instead of drawing, the
  writer picks real meme templates: Imgflip's 100 most used pictures (Drake, Two Buttons, Distracted Boyfriend, Gru's
  Plan, Monkey Puppet...) and its popular animated ones (short clips), and finds any other by search, Indian film and
  TV memes included (Hera Pheri, Jethalal, "Paisa hi paisa hoga"...). The app downloads the picture or clip and writes
  your lines into the template's own text boxes, where its text belongs; clips loop under the line, muted. Where no
  template fits (or you're offline), the meme is drawn as before. Templates about politicians are never used. These are
  other people's pictures and film or TV clips: they can bring copyright claims, which is why it's your choice.
- Script Videos and Shoot never change your words: memes only go on lines that already set one up.

## Shoot: you on camera (tab "Shoot")

Film yourself with your phone's own camera app while this computer is your teleprompter.

1. **New shoot**: paste your script (and a hook if you want a cinematic opening), pick 16:9 or 9:16 and your
   language. The script is cut into short shots of one or two lines; Claude decides which lines show you and which
   show B-roll (footage, graphics, AI stills) while your voice goes on. Tap a line's tag to change it.
2. **Teleprompter**: open it on this computer at `http://localhost:8000` (browsers only allow the microphone there or
   over https) and put the phone right above the text. It highlights each word as you say it, keeps your line near
   the camera, and survives ad-libs and misheard words. Space turns listening on/off, → / ← move between shots,
   R starts a shot again, M mirrors for a teleprompter glass.
3. **Upload the best take of each shot**, from the phone over Wi-Fi or from this computer. Each take is checked:
   how much of the script was heard, which words were missed, HDR and orientation. Hindi and Hinglish takes are heard
   by a bigger offline speech model (about 0.5 GB, downloaded with the first such take) and matched by sound, so
   'commands' said in a Hinglish sentence counts even when it's written 'कमान्ट्स'. Takes uploaded before an
   improvement to this check are checked again when you open the shoot.
4. **Make the video**: your takes are the voice and the on-camera picture, with a punch-in on every other take; the
   other lines get their B-roll, plus captions from your words, music, sound design and the cinematic hook.
5. **Your voice** (optional, free, on this computer; install the voice engine once from the Shoot tab, about 6 GB):
   - **Clean my voice**: noise, hum and room echo taken out and a clearer studio tone, with the timing kept to the
     sample so your lips stay in sync.
   - **Rebuild words I skipped, in my own voice**: your voice is cloned from your takes; the line is spoken in it, the
     missing words are cut out and put into your take, and the line is checked again. A fixed line that was on camera
     shows its B-roll. A line with most of its words missing needs a new take.
   - Each take lists the words to look at, with ▶ to hear that moment and a **Rebuild in my voice** box: ticked for
     words not heard, unticked for words heard as another word ("Heard 'रहेगा' for paayega": speech-to-text often
     mishears clearly spoken Hinglish). Tick or untick any of them; the video rebuilds exactly the ticked ones.

## Shorts Studio (tab "Shorts+")

Full-screen 9:16 Shorts, one or a series of parts, each at most 30 s (45 or 60 if you pick): part 1 hooks and ends on a
cliffhanger, part 2 picks it up, and so on. Each part lands in the library as its own Short. Mix any of:

- **Script**: Claude writes it (an original story, a true story, an explainer, this week's news or comedy; true ones
  are researched and fact-checked; 1-6 parts), or paste your own (every word kept; mark parts with a `Part 2` line or
  let the app cut it by length).
- **Voice**: English, Hinglish or Hindi (Sarvam voices with your key, else the free Madhur/Andrew voices).
- **Words on screen**: English, or the voice's own language.
- **Look**: motion graphics like the long videos (numbers, charts, timelines, steps, icons, 3D, photo backdrops, laid out
  for the tall screen), AI animation in every shot or only the key shots, AI pictures with camera moves, or stock footage.
  The AI looks need the AI engine (Anim tab); stock footage needs a Pexels key.

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
  sfx.py            whoosh and pop sound effects, made on the fly (and the hook's boom, riser, drone)
  cinehook.py       the cinematic hook: rules, timing, AI stills, sound design, silence
  memes.py          the meme option: formats, the funny-explainer rules, checks
  memeweb.py        real meme templates and clips from imgflip.com (list, search, text boxes, download)
  shoot.py          the Shoot tab: shots, Claude's on-camera plan, your takes, the edit
  notifier.py       Telegram + GitHub run summary
  pipeline.py       runs all steps with verify-and-retry
remotion/           the video edit (React + Remotion), rendered by video.py
  src/Reel.tsx      the "Reel" composition: layers, audio, sound effects
  src/Graphics.tsx  stat / chart / compare / keyword graphics
  src/Captions.tsx  word-by-word pop captions
  src/HookTitle.tsx the opening hook card
  src/Background.tsx footage cuts, punch-in zoom, scene-change flash
  src/cine/         the cinematic hook's grades, film texture, typed labels, transitions, subscribe card
  src/long/Meme.tsx the memes, drawn in code with the Toon editor's cartoon people
```

To preview or tweak the edit: `cd remotion && npm run studio` opens Remotion Studio with sample props (`src/demo.ts`). The Python pipeline renders with `remotion render src/index.ts Reel out.mp4 --props=props.json --public-dir=<video folder>`.

## Notes

- **Posting is up to you.** Save the video from the app and upload it in Instagram or YouTube. Auto-posting needs a YouTube API app or an Instagram Business account; it can be added later.
- **"Not AI-looking" has limits.** Stock footage, a natural script, and varied voice and pacing get close to a real faceless channel. For the most human result, record the voiceover yourself: replace `reel.mp4`'s voice, or ask for a "use my recording" option.
- **Always watch before posting.** Verification catches a lot, but trending news can be sensitive.
