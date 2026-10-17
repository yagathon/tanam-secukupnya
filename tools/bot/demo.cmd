@echo off
rem Demo video: the bot types the scenario into the sandbox through the real UI, in a visible Chrome window.
rem Run from a Windows terminal (VS Code is fine):   tools\bot\demo.cmd
rem   no arguments    = clear the local sandbox, load the scenario setup, play 14 days, 2 s per day
rem   with arguments  = passed to bot.mjs as they are, e.g.  tools\bot\demo.cmd --days 7 --pause 3000   (continue)
rem The API (:8100) and the UI (:3100) run in WSL; each is started in its own window if it is not up yet.
setlocal
cd /d "%~dp0"

if not exist node_modules\playwright (
  echo Installing the bot's packages...
  call npm install --no-audit --no-fund || exit /b 1
)

curl -s -o nul http://localhost:8100/api/health
if errorlevel 1 (
  echo Starting the API in WSL...
  start "tanam-api :8100" wsl.exe -d Ubuntu bash -lc "cd /mnt/c/tfi/tanam-secukupnya/backend && AUTH=off ~/.local/bin/uv run uvicorn app.main:app --port 8100"
)
curl -s -o nul http://localhost:3100/sandbox
if errorlevel 1 (
  echo Starting the UI in WSL...
  start "tanam-ui :3100" wsl.exe -d Ubuntu bash -lc "cd /mnt/c/tfi/tanam-secukupnya/frontend && NEXT_PUBLIC_AUTH=off WATCHPACK_POLLING=true npx next dev --port 3100"
)

echo Waiting for the API and the UI...
:wait
ping -n 4 127.0.0.1 >nul
curl -s -o nul -f http://localhost:8100/api/health || goto wait
curl -s -o nul -f http://localhost:3100/sandbox || goto wait

if "%~1"=="" (
  node bot.mjs --reset --days 14 --pause 2000
) else (
  node bot.mjs %*
)
