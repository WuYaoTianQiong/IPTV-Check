param(
    [ValidateSet("prod", "dev")]
    [string]$Mode = "prod",
    [int]$Port = 9528,
    [switch]$NoBrowser
)

$projectRoot = $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  IPTV-Check Launcher ($Mode mode)" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

function Stop-PortProcess {
    param([int]$Port)
    $existing = netstat -ano 2>$null | Select-String ":$Port .*LISTENING"
    if ($existing) {
        $pid = ($existing -split '\s+')[-1]
        if ($pid -match '^\d+$') {
            $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Stopping old process: $($proc.ProcessName) (PID: $pid)" -ForegroundColor Yellow
                Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
                Start-Sleep -Milliseconds 500
            }
        }
    }
}

function Stop-DevWindows {
    Get-Process -Name cmd -ErrorAction SilentlyContinue | Where-Object {
        $_.MainWindowTitle -like "IPTV-Check Frontend*" -or $_.MainWindowTitle -like "IPTV-Check Backend*"
    } | ForEach-Object {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Stopping window: $($_.MainWindowTitle)" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
    }
}

function Install-FrontendDeps {
    $vitePkg = Join-Path $frontendDir "node_modules\vite\package.json"
    if (-not (Test-Path $vitePkg)) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Installing frontend dependencies..." -ForegroundColor Yellow
        Push-Location $frontendDir
        npm install
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] npm install failed, removing node_modules and retrying..." -ForegroundColor Yellow
            Remove-Item -Recurse -Force "node_modules" -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 1
            npm install
            if ($LASTEXITCODE -ne 0) {
                Write-Host "[$(Get-Date -Format 'HH:mm:ss')] npm install FAILED after retry!" -ForegroundColor Red
                Write-Host "  Close IDE/terminal that may lock node_modules, then run again." -ForegroundColor Red
                Pop-Location
                exit 1
            }
        }
        Pop-Location
    }
}

if ($Mode -eq "prod") {
    Stop-PortProcess -Port $Port
    Stop-DevWindows
    Start-Sleep -Seconds 1

    Install-FrontendDeps

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Building frontend..." -ForegroundColor Yellow
    Push-Location $frontendDir
    # 构建产物按 vite.config.js 输出到 backend/iptv_check/static（后端 serve 的目录）
    npx vite build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Frontend build FAILED!" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Frontend build OK" -ForegroundColor Green

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting server: http://127.0.0.1:$Port" -ForegroundColor Cyan
    $pythonCmd = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonCmd)) { $pythonCmd = "python" }
    $env:PYTHONPATH = $backendDir
    # 服务日志统一写入 logs\（已在 .gitignore 忽略），避免散落源码目录
    $logDir = Join-Path $projectRoot "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $proc = Start-Process -FilePath $pythonCmd -ArgumentList "-m", "iptv_check", "--port", $Port -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "server_$stamp.out.log") -RedirectStandardError (Join-Path $logDir "server_$stamp.err.log") -PassThru
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Server logs: $logDir (PID $($proc.Id))" -ForegroundColor DarkGray

    Start-Sleep -Seconds 3
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port" }

    Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] Server running: http://127.0.0.1:$Port" -ForegroundColor Green
}
elseif ($Mode -eq "dev") {
    Stop-PortProcess -Port $Port
    Stop-DevWindows
    Start-Sleep -Seconds 1

    Install-FrontendDeps

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting frontend (Vite)..." -ForegroundColor Yellow
    Start-Process -FilePath "cmd" -ArgumentList "/c", "title IPTV-Check Frontend && cd /d `"$frontendDir`" && npx vite --port 5173" -WorkingDirectory $frontendDir

    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] Starting backend (Uvicorn --reload)..." -ForegroundColor Yellow
    $pythonCmd = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $pythonCmd)) { $pythonCmd = "python" }
    $env:PYTHONPATH = $backendDir
    Start-Process -FilePath "cmd" -ArgumentList "/c", "title IPTV-Check Backend && cd /d `"$backendDir`" && $pythonCmd -m uvicorn iptv_check.server.app:create_app --factory --host 127.0.0.1 --port $Port --reload" -WorkingDirectory $backendDir

    Start-Sleep -Seconds 4
    if (-not $NoBrowser) { Start-Process "http://localhost:5173" }

    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "  Dev Mode:" -ForegroundColor Cyan
    Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
    Write-Host "  Backend:  http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "  API Docs: http://127.0.0.1:$Port/docs" -ForegroundColor Green
    Write-Host "========================================`n" -ForegroundColor Cyan
}

Write-Host "Tip: Close this window or press Ctrl+C to stop" -ForegroundColor DarkGray
