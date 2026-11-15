@echo off
rem Start Reel Studio on Windows. First run installs everything.
cd /d "%~dp0"
if not exist .venv (
  echo First run: setting up, takes a minute...
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\python -m pip install -q --upgrade pip
)
rem Every start: installs anything new that a git pull added (quick when nothing is missing).
.venv\Scripts\python -m pip install -q -r requirements.txt
rem Installs the editor on the first run, and again whenever a git pull changed its packages.
if not exist remotion\node_modules\.bin\remotion.cmd (call :install_editor) else (fc /b remotion\package-lock.json remotion\node_modules\.installed-lock >nul 2>nul || call :install_editor)
if not exist .env copy .env.example .env >nul
where claude >nul 2>nul || echo Note: Claude Code not found. Install it from https://claude.com/claude-code and run "claude" once to log in, or put ANTHROPIC_API_KEY in .env.
.venv\Scripts\python -m reelgen serve %*
rem 75 = closed by "Update and restart": a new window opens with the updated app.
if errorlevel 75 if not errorlevel 76 exit
pause
goto :eof

rem The video editor (Remotion) needs Node.js. Without it videos still work, using a simpler edit.
:install_editor
where npm >nul 2>nul || (
  echo Note: Node.js not found, so videos use the simpler edit without animated graphics.
  echo       Install Node.js LTS from https://nodejs.org and start again to get the full edit.
  exit /b
)
echo Installing the video editor packages, takes a few minutes...
pushd remotion
call npm install --no-audit --no-fund --loglevel=error
if not errorlevel 1 copy /y package-lock.json node_modules\.installed-lock >nul
if not errorlevel 1 call node_modules\.bin\remotion browser ensure
popd
exit /b
