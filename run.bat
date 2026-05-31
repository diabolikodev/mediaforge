@echo off
setlocal enabledelayedexpansion

title MediaForge Local

echo.
echo ===============================
echo        MediaForge Local
echo ===============================
echo.

set "PY_CMD="

py --version >nul 2>&1
if %errorlevel%==0 set "PY_CMD=py"

if not defined PY_CMD (
    python --version >nul 2>&1
    if %errorlevel%==0 set "PY_CMD=python"
)

if not defined PY_CMD (
    echo Python was not found.
    echo Install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('%PY_CMD% --version 2^>^&1') do set "PY_VERSION=%%i"
echo Using !PY_VERSION!

if not exist ".venv" (
    echo Creating virtual environment...
    %PY_CMD% -m venv .venv
)

call .venv\Scripts\activate >nul

if not exist ".venv\.mediaforge_deps_ok" (
    echo Installing dependencies...
    python -m pip install --upgrade pip -q
    pip install -r requirements.txt -q

    if errorlevel 1 (
        echo.
        echo Dependency installation failed.
        pause
        exit /b 1
    )

    echo ok > ".venv\.mediaforge_deps_ok"
) else (
    echo Dependencies ready.
)

ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo FFmpeg not found. MP3/M4A/MP4 conversion may fail.
) else (
    echo FFmpeg detected.
)

echo.
echo Starting MediaForge...
echo Opening http://127.0.0.1:8787
echo Press CTRL+C to stop.
echo.

python run.py

pause
