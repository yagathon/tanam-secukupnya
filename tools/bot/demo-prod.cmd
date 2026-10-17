@echo off
rem Demo video against prod (https://tanam-secukupnya.web.app): the bot types the scenario into its own sandbox
rem through the real UI, in a visible browser. Needs Node.js (https://nodejs.org) and Chrome or Edge.
rem   demo-prod.cmd                       clear the bot's sandbox, load the scenario setup, play 14 days, 2 s per day
rem   demo-prod.cmd --days 7 --pause 3000 continue from where the last run stopped
rem   add --slow 250 for slower typing; delete the "profile" folder for a brand-new visitor
setlocal
cd /d "%~dp0"
where node >nul 2>nul || (echo Node.js is not installed: get the LTS from https://nodejs.org & exit /b 1)
if not exist node_modules\playwright (
  echo Installing the bot's packages...
  call npm install --no-audit --no-fund || exit /b 1
)
set CHANNEL=msedge
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set CHANNEL=chrome
if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set CHANNEL=chrome
if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set CHANNEL=chrome
if "%~1"=="" (
  node bot.mjs --ui https://tanam-secukupnya.web.app --channel %CHANNEL% --reset --days 14 --pause 2000
) else (
  node bot.mjs --ui https://tanam-secukupnya.web.app --channel %CHANNEL% %*
)
