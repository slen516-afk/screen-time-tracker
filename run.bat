@echo off
cd /d "%~dp0"
title ScreenTime PC Launcher
cls

echo ============================================================
echo      ScreenTime PC - iOS Style Screen Time Tracker
echo ============================================================
echo [*] Starting background active tracking engine and web server...
echo [*] The dashboard page will open automatically in your default browser...
echo.
echo [*] NOTE: Keeping this terminal open is required for Screen Time tracking.
echo ============================================================
echo.

"C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe" -u app.py > "%~dp0startup_log.txt" 2>&1

echo.
echo ============================================================
echo [*] ScreenTime PC service stopped. Double-click this file to restart.
echo.
pause
