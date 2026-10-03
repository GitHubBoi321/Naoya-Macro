@echo off
title Zen'in Elite Macro v1.4 Setup
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    set PY=py
) else (
    set PY=python
)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo Installation failed. Make sure Python is installed and added to PATH.
    pause
    exit /b 1
)
%PY% zenin_elite_macro_v1_4.py
pause
