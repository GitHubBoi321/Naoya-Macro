@echo off
title Zen'in Elite Macro v1.9
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py zenin_elite_macro_v1_9.py
) else (
    python zenin_elite_macro_v1_9.py
)
pause
