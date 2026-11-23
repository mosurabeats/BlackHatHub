# Executive Hub - Windows launcher (PowerShell). Started by START-WINDOWS.bat.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Venv = Join-Path $Root ".venv"

function Say($m) { Write-Host "==> $m" -ForegroundColor Green }
function Die($m) { Write-Host "ERROR: $m" -ForegroundColor Red; exit 1 }

# Python 3.12+
$py = $null
foreach ($cand in @("py -3.13", "py -3.12", "python")) {
  try {
    $parts = $cand.Split(" ")
    $ok = & $parts[0] $parts[1..($parts.Length-1)] -c "import sys; print(sys.version_info >= (3,12))" 2>$null
    if ($ok -eq "True") { $py = $cand; break }
  } catch {}
}
if (-not $py) { Die "Python 3.12+ is required. Install it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH') and run again." }
Say "Using $py"

$vpy = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $vpy)) {
  Say "Creating private Python environment (first run only)..."
  $parts = $py.Split(" ")
  & $parts[0] $parts[1..($parts.Length-1)] -m venv $Venv
}
$hash = (Get-FileHash "backend\requirements.txt").Hash
$hashFile = Join-Path $Venv ".req-hash"
if (-not (Test-Path $hashFile) -or (Get-Content $hashFile) -ne $hash) {
  Say "Installing dependencies..."
  & $vpy -m pip install --quiet --upgrade pip
  & $vpy -m pip install --quiet -r backend\requirements.txt
  if ($LASTEXITCODE -ne 0) { Die "Dependency install failed (check internet connection)" }
  Set-Content $hashFile $hash
}
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Say "Created .env" }
if (-not (Test-Path "frontend\dist\index.html")) { Die "Prebuilt web interface missing (frontend\dist). Re-download the release ZIP." }

$port = 8765
$line = Select-String -Path ".env" -Pattern "^EXECHUB_PORT=(\d+)" -ErrorAction SilentlyContinue
if ($line) { $port = $line.Matches[0].Groups[1].Value }

try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/ping" -TimeoutSec 2 | Out-Null; Say "Already running."; Start-Process "http://localhost:$port/"; exit 0 } catch {}

Set-Location (Join-Path $Root "backend")
& $vpy -m app.cli init
if ($LASTEXITCODE -ne 0) { Die "Database initialization failed" }
$proc = Start-Process -FilePath $vpy -ArgumentList "-m", "app.server" -NoNewWindow -PassThru
for ($i = 0; $i -lt 60; $i++) {
  try { Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$port/api/ping" -TimeoutSec 1 | Out-Null; break } catch { Start-Sleep -Milliseconds 500 }
}
Say "Executive Hub is running: http://localhost:$port/"
Say "Keep this window open. Press Ctrl+C to stop."
Start-Process "http://localhost:$port/"
try { Wait-Process -Id $proc.Id } finally { if (-not $proc.HasExited) { Stop-Process -Id $proc.Id } }
