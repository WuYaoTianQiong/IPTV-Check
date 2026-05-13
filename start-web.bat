@echo off
chcp 65001 >nul

echo.
echo ========================================
echo   IPTV-Check Web Launcher
echo ========================================
echo.

set "PORT=%~1"
if not defined PORT set "PORT=9529"

echo [%TIME%] Killing old process on port %PORT%...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    echo [%TIME%] Terminating PID: %%a
    taskkill /F /PID %%a >nul 2>&1
    timeout /t 1 /nobreak >nul
)

echo [%TIME%] Starting web server...
echo [%TIME%] URL: http://127.0.0.1:%PORT%
echo.

cd /d "%~dp0"
start "" python -m iptv_check --port %PORT%

timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:%PORT%

echo.
echo ========================================
echo   Server started. Press Ctrl+C to stop.
echo ========================================
echo.

pause >nul
