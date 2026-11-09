@echo off
set PYTHONIOENCODING=utf-8
if "%VOD_PORT%"=="" set VOD_PORT=8765
start "" http://127.0.0.1:%VOD_PORT%
"%~dp0.venv\Scripts\python.exe" "%~dp0web.py"
