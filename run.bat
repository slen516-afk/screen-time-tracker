@echo off
title ScreenTime PC Launcher
cls

echo ============================================================
echo      ScreenTime PC - iOS Style Screen Time Tracker
echo ============================================================
echo.
echo [*] Checking and ensuring Python dependencies are installed...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] Warning: Dependency check failed, attempting to start...
)

echo [*] Starting background active tracking engine and web server...
echo [*] The dashboard page will open automatically in your default browser...
echo.
echo [*] NOTE: Keeping this terminal open is required for Screen Time tracking.
echo ============================================================
echo.

python app.py

echo.
echo ============================================================
echo [*] ScreenTime PC service stopped. Double-click this file to restart.
echo.
pause
