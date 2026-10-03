@echo off
title Zen'in Elite Macro v2.0
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py zenin_elite_macro_v2_0.py
) else (
    python zenin_elite_macro_v2_0.py
)
pause
