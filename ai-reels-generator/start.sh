#!/usr/bin/env bash
# Start Reel Studio on macOS / Linux. First run installs everything.
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "First run: setting up (takes a minute)..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
fi
# Every start: installs anything new that a git pull added (quick when nothing is missing).
.venv/bin/pip install -q -r requirements.txt
# The video editor (Remotion) needs Node.js. Without it videos still work, using a simpler edit.
if [ ! -e remotion/node_modules/.bin/remotion ]; then
  if command -v npm >/dev/null; then
    echo "First run: installing the video editor (takes a few minutes)..."
    (cd remotion && npm install --no-audit --no-fund --loglevel=error && node_modules/.bin/remotion browser ensure) \
      || echo "Note: the video editor didn't install; videos will use the simpler edit."
  else
    echo "Note: Node.js not found, so videos use the simpler edit without animated graphics."
    echo "      Install Node.js LTS from https://nodejs.org and start again to get the full edit."
  fi
fi
[ -f .env ] || cp .env.example .env
command -v claude >/dev/null || echo "Note: Claude Code not found. Install it (https://claude.com/claude-code) and run 'claude' once to log in, or put ANTHROPIC_API_KEY in .env."
exec .venv/bin/python -m reelgen serve "$@"
