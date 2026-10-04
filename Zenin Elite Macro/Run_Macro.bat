@echo off
title Zen'in Elite Macro v3.20
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py zenin_elite_macro_v3_20.py
) else (
    python zenin_elite_macro_v3_20.py
)
pause
