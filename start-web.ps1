param(
    [int]$Port = 9529,
    [switch]$NoBrowser
)

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  IPTV-Check Web 启动脚本" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 检查端口 $Port 是否被占用..." -ForegroundColor Yellow

$existingProcess = netstat -ano | Select-String ":$Port .*LISTENING"
if ($existingProcess) {
    $pid = ($existingProcess -split '\s+')[-1]
    if ($pid -match '^\d+$') {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 发现旧进程: $($proc.ProcessName) (PID: $pid)" -ForegroundColor Yellow
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 500
            Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 旧进程已终止" -ForegroundColor Green
        }
    }
} else {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 端口 $Port 未被占用" -ForegroundColor Green
}

Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] 启动 Web 服务..." -ForegroundColor Yellow
Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 地址: http://127.0.0.1:$Port`n" -ForegroundColor Cyan

$pythonCmd = "$projectRoot\.venv\Scripts\python.exe"
if (Test-Path $pythonCmd) {
    $env:PYTHONPATH = $projectRoot
    Start-Process -FilePath $pythonCmd -ArgumentList "-m", "iptv_check", "--port", $Port, $(if ($NoBrowser) { "--no-browser" }) -WorkingDirectory $projectRoot
} else {
    $pythonCmd = "python"
    Start-Process -FilePath $pythonCmd -ArgumentList "-m", "iptv_check", "--port", $Port, $(if ($NoBrowser) { "--no-browser" }) -WorkingDirectory $projectRoot
}

Start-Sleep -Seconds 2

if (-not $NoBrowser) {
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] 打开浏览器..." -ForegroundColor Yellow
    Start-Process "http://127.0.0.1:$Port"
}

Write-Host "`n[$(Get-Date -Format 'HH:mm:ss')] 服务已启动完成" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan
Write-Host "提示: 如需停止服务，请关闭控制台窗口或按 Ctrl+C" -ForegroundColor DarkGray
