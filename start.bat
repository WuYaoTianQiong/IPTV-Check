@echo off

echo.
echo ========================================
echo   IPTV-Check Launcher
echo ========================================
echo.

cd /d "%~dp0"

set "MODE=%~1"
if /i "%MODE%"=="" set "MODE=prod"
if /i "%MODE%"=="dev" goto :dev
if /i "%MODE%"=="prod" goto :prod

echo Usage: %~nx0 [prod^|dev] [port]
echo   prod  - Build frontend and start server (default)
echo   dev   - Dev mode with hot reload
goto :eof

:prod
set "PORT=%~2"
if not defined PORT set "PORT=9529"

echo [%TIME%] Stopping old process on port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)
timeout /t 1 /nobreak >nul

if not exist "frontend\node_modules\vite\package.json" (
    echo [%TIME%] Installing frontend dependencies...
    cd frontend
    call npm install
    if errorlevel 1 (
        echo [%TIME%] npm install failed, removing node_modules and retrying...
        rd /s /q node_modules 2>nul
        call npm install
        if errorlevel 1 (
            echo [%TIME%] npm install FAILED after retry!
            echo         Close IDE/terminal that may lock node_modules, then run again.
            cd ..
            pause
            exit /b 1
        )
    )
    cd ..
)

echo [%TIME%] Building frontend...
cd frontend
call npx vite build
if errorlevel 1 (
    echo [%TIME%] Frontend build FAILED!
    cd ..
    pause
    exit /b 1
)
cd ..

echo [%TIME%] Frontend build OK

echo [%TIME%] Starting server: http://127.0.0.1:%PORT%
cd backend
start "IPTV-Check" cmd /c "python -m iptv_check --port %PORT%"
cd ..

echo [%TIME%] Waiting for server to be ready...
set "READY=0"
for /L %%i in (1,1,15) do (
    timeout.exe /t 1 >nul
    netstat -ano 2>nul | findstr ":%PORT% " | findstr "LISTENING" >nul 2>&1
    if not errorlevel 1 (
        echo [%TIME%] Server is ready
        set "READY=1"
        goto :ready
    )
)

:ready
if "%READY%"=="0" (
    echo [%TIME%] WARNING: Server may not have started properly
    echo         Check the IPTV-Check window for error messages
)

timeout /t 1 /nobreak >nul
start "" http://127.0.0.1:%PORT%

echo.
echo ========================================
echo   Server running: http://127.0.0.1:%PORT%
echo   Press any key to stop...
echo ========================================
pause >nul
taskkill /FI "WINDOWTITLE eq IPTV-Check*" /F >nul 2>&1
goto :eof

:dev
set "PORT=%~2"
if not defined PORT set "PORT=9529"

echo [%TIME%] Stopping old process on port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo [%TIME%] Stopping old dev windows...
taskkill /FI "WINDOWTITLE eq IPTV-Check Frontend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq IPTV-Check Backend*" /F >nul 2>&1
timeout /t 1 /nobreak >nul

if not exist "frontend\node_modules\vite\package.json" (
    echo [%TIME%] Installing frontend dependencies...
    cd frontend
    call npm install
    if errorlevel 1 (
        echo [%TIME%] npm install failed, removing node_modules and retrying...
        rd /s /q node_modules 2>nul
        call npm install
        if errorlevel 1 (
            echo [%TIME%] npm install FAILED after retry!
            echo         Close IDE/terminal that may lock node_modules, then run again.
            cd ..
            pause
            exit /b 1
        )
    )
    cd ..
)

echo [%TIME%] Starting frontend dev server (Vite)...
cd frontend
start "IPTV-Check Frontend" cmd /c "npx vite --port 5173"
cd ..

echo [%TIME%] Starting backend dev server (Uvicorn --reload)...
cd backend
start "IPTV-Check Backend" cmd /c "python -m uvicorn iptv_check.server.app:create_app --factory --host 127.0.0.1 --port %PORT% --reload"
cd ..

timeout /t 4 /nobreak >nul
start "" http://localhost:5173

echo.
echo ========================================
echo   Dev Mode:
echo   Frontend: http://localhost:5173
echo   Backend:  http://127.0.0.1:%PORT%
echo   API Docs: http://127.0.0.1:%PORT%/docs
echo   Press any key to stop...
echo ========================================
pause >nul
taskkill /FI "WINDOWTITLE eq IPTV-Check Frontend*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq IPTV-Check Backend*" /F >nul 2>&1
goto :eof
