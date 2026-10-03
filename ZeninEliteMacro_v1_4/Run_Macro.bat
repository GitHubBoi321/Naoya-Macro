@echo off
title Zen'in Elite Macro v1.4
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py zenin_elite_macro_v1_4.py
) else (
    python zenin_elite_macro_v1_4.py
)
pause
