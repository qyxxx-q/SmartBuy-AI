$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$url = 'http://127.0.0.1:8000'
if (-not (Test-Path -LiteralPath $pythonExe) -or -not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
    & (Join-Path $projectRoot 'Setup-SmartBuy.ps1')
}
$running = $false
try { $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2; $running = $health.status -eq 'ok' } catch {}
if (-not $running) {
    $backendDir = Join-Path $projectRoot 'backend'
    $process = Start-Process -FilePath $pythonExe -ArgumentList 'app.py' -WorkingDirectory $backendDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $backendDir 'server.out.log') -RedirectStandardError (Join-Path $backendDir 'server.err.log') -PassThru
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Start-Sleep -Milliseconds 500
        if ($process.HasExited) { throw 'Startup failed. Check backend/server.err.log.' }
        try { $health = Invoke-RestMethod -Uri "$url/api/health" -TimeoutSec 2; if ($health.status -eq 'ok') { $running = $true; break } } catch {}
    }
    if (-not $running) { throw 'Startup timed out. Check backend/server.err.log.' }
}
Write-Host "SmartBuy AI is running at $url"
Start-Process $url
