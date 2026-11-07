@echo off
set PYTHONIOENCODING=utf-8
start "" http://127.0.0.1:8765
"%~dp0.venv\Scripts\python.exe" "%~dp0web.py"
