$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) { & $launcher.Source -3 -m venv (Join-Path $projectRoot '.venv') }
    else { & python -m venv (Join-Path $projectRoot '.venv') }
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.10 or newer first.' }
}
& $venvPython -c 'import sys; assert sys.version_info >= (3,10), "Python 3.10+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ required. Recreate .venv with a newer Python.' }
& $venvPython -m pip install -r (Join-Path $projectRoot 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location (Join-Path $projectRoot 'frontend')
try {
    & npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed. Install Node.js 20.19+ or 22.12+.' }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
Write-Host 'Setup complete. Run start-smartbuy.cmd to open the website.'
