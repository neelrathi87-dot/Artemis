@echo off
title Artemis Autonomous Mobile Agent
cd /d "%~dp0"

echo ========================================================
echo        Artemis Autonomous Mobile Agent
echo ========================================================
echo.

:: Add uv to PATH
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

:: Ensure wireless phone connection if configured
if not defined ADB_DEVICE_SERIAL (
    if exist .env (
        for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
            if "%%A"=="ADB_DEVICE_SERIAL" set "ADB_DEVICE_SERIAL=%%B"
        )
    )
)

if defined ADB_DEVICE_SERIAL (
    echo [*] Checking wireless connection to %ADB_DEVICE_SERIAL%...
    adb connect %ADB_DEVICE_SERIAL% >nul 2>&1
)

:: Launch Artemis UI server (opens browser automatically)
echo Starting Artemis UI on http://localhost:8000 ...
uv run python -m artemis ui

if errorlevel 1 (
    echo.
    echo [!] Artemis stopped with an error code.
    pause
)
