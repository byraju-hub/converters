@echo off
rem Raju's Converters - one-click setup (Windows). Double-click this file.
title Raju's Converters Setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
echo.
pause
