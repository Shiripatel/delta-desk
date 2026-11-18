@echo off
rem Delta Desk on this machine: real delayed quotes (Yahoo), synthetic F&O desk in paper mode.
rem Double-click, then open http://127.0.0.1:8000/   (Ctrl C in this window stops it)
cd /d "%~dp0.."
if not exist .env (echo DD_QUOTES=yahoo> .env & echo DD_FEED=synthetic>> .env & echo DD_MODE=paper>> .env)
set DD_QUOTES=yahoo
uv run deltadesk serve --port 8000 --speed 120
