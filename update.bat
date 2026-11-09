@echo off
rem Raju's Converters - update (Windows). Double-click this file.
title Raju's Converters Update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
echo.
pause
