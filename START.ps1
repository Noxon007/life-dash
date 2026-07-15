# Life-Dash — Start-Skript (Backend hochfahren + Frontend öffnen)
# Aufruf:  powershell -ExecutionPolicy Bypass -File .\START.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = "http://127.0.0.1:8000/"   # Frontend wird vom Backend ausgeliefert (frontend/)

# Python aus dem miniforge-Env py313
$py = "C:\Users\phili\miniforge3\envs\py313\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "Python-Env nicht gefunden: $py" -ForegroundColor Red
    Write-Host "Passe die Variable \$py im Skript an dein Environment an." -ForegroundColor Yellow
    exit 1
}

# Abhaengigkeiten sicherstellen (nur beim ersten Mal langsam)
Write-Host "Pruefe Abhaengigkeiten..." -ForegroundColor Cyan
& $py -m pip install -q -r (Join-Path $backend "requirements.txt")

# Noch laufende Instanzen auf Port 8000 stoppen (sauberer Neustart)
$listening = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "Stoppe laufende Instanz(en) auf Port 8000..." -ForegroundColor Yellow
    foreach ($procId in ($listening.OwningProcess | Sort-Object -Unique)) {
        # uvicorn --reload: der Listener ist ein Kindprozess — den Eltern-uvicorn
        # mit beenden, sonst startet der Reloader den Listener sofort neu
        $proc   = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        $parent = if ($proc) { Get-CimInstance Win32_Process -Filter "ProcessId=$($proc.ParentProcessId)" -ErrorAction SilentlyContinue } else { $null }
        $rootPid = if ($parent -and $parent.CommandLine -match "uvicorn") { $parent.ProcessId } else { $procId }
        & taskkill /PID $rootPid /T /F 2>$null | Out-Null
    }
    Start-Sleep -Seconds 1
}

Write-Host "Starte Backend (uvicorn) auf http://127.0.0.1:8000 ..." -ForegroundColor Cyan
# --reload: Codeaenderungen werden ohne manuellen Neustart uebernommen
Start-Process -FilePath $py `
    -ArgumentList "-m","uvicorn","app.main:app","--host","127.0.0.1","--port","8000","--reload" `
    -WorkingDirectory $backend -WindowStyle Minimized
Start-Sleep -Seconds 4

# Health-Check
try {
    $h = Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 5
    Write-Host "Backend OK  (KI: $($h.ai_provider), Auth: $($h.auth_mode), DB: $($h.database))" -ForegroundColor Green
} catch {
    Write-Host "Backend antwortet noch nicht - gib ihm einen Moment und lade das Frontend neu." -ForegroundColor Yellow
}

# Frontend im Standardbrowser oeffnen
Write-Host "Oeffne Frontend: $frontend" -ForegroundColor Cyan
Start-Process $frontend

Write-Host ""
Write-Host "Life-Dash laeuft:" -ForegroundColor Green
Write-Host "  Frontend : $frontend"
Write-Host "  API-Docs : http://127.0.0.1:8000/docs"
Write-Host "  Health   : http://127.0.0.1:8000/health"
