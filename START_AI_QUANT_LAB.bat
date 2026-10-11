@echo off
setlocal
cd /d "%~dp0"
title AI Quant Lab V4
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start_voice_dashboard.ps1"
if errorlevel 1 (
  echo.
  echo AI Quant Lab stopped with an error. Read the message above.
  pause
)
endlocal
