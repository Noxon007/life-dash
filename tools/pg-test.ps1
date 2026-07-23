# Die Testsuite gegen ein echtes PostgreSQL fahren — das, worauf Life-Dash
# betrieben wird (`docker-compose.yml` startet `postgres:18-alpine`).
#
# Warum überhaupt: die 590 Tests laufen auf SQLite. Eine ganze Fehlerklasse
# fällt dort nicht auf und beim ersten echten Start sofort — native Enum-Typen,
# JSON gegen JSONB, `round()` auf `double precision` (der Befund aus
# Anmerkung 119), der PostgreSQL-Zweig von `_relax_not_null`.
#
#   pwsh tools/pg-test.ps1            # Cluster hochfahren, Tests, wieder runter
#   pwsh tools/pg-test.ps1 -Keep      # Cluster danach weiterlaufen lassen
#   pwsh tools/pg-test.ps1 -Stop      # nur stoppen und aufräumen
#
# **Kein Docker, kein Adminrecht, kein Passwort.** Statt den installierten
# Dienst anzufassen, legt dieses Skript mit denselben Binärdateien einen
# EIGENEN, isolierten Cluster in `backend/_pgtest/` an — eigener Port 55432,
# `trust`-Auth nur auf localhost, danach wieder gestoppt. Der Dienst auf 5432
# (mit seinem Passwort, das der stille Installer gesetzt hat) bleibt
# unberührt. Der eigene Port ist zugleich der Riegel: eine Suite, die das
# Schema löscht, trifft den Standardport gar nicht erst.
param(
    [switch]$Keep,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"

$Port = 55432
$Db   = "lifedash_test"
$Py   = "C:\Users\phili\miniforge3\envs\py313\python.exe"
$Repo = Split-Path -Parent $PSScriptRoot
$Data = Join-Path $Repo "backend\_pgtest\data"
$Log  = Join-Path $Repo "backend\_pgtest\server.log"

# Die Binärdateien des installierten PostgreSQL suchen — höchste Version.
$pgRoot = Get-ChildItem "C:\Program Files\PostgreSQL" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
if (-not $pgRoot) { throw "PostgreSQL nicht gefunden. Mit 'winget install PostgreSQL.PostgreSQL.18' installieren." }
$Bin     = Join-Path $pgRoot.FullName "bin"
$initdb  = Join-Path $Bin "initdb.exe"
$pg_ctl  = Join-Path $Bin "pg_ctl.exe"
$createdb= Join-Path $Bin "createdb.exe"
$psql    = Join-Path $Bin "psql.exe"

function Stop-Cluster {
    if (Test-Path (Join-Path $Data "postmaster.pid")) {
        & $pg_ctl -D $Data -m fast stop 2>$null | Out-Null
    }
}

if ($Stop) {
    Stop-Cluster
    Remove-Item (Join-Path $Repo "backend\_pgtest") -Recurse -Force -ErrorAction SilentlyContinue
    "Test-Cluster gestoppt und entfernt."
    exit 0
}

# Cluster neu aufsetzen, falls noch keiner steht. Bewusst NICHT jedes Mal neu:
# `initdb` kostet spürbar, und geleert wird ohnehin je Test (conftest:
# TRUNCATE). Ein vorhandener Cluster wird also weiterbenutzt.
if (-not (Test-Path (Join-Path $Data "PG_VERSION"))) {
    New-Item -ItemType Directory -Force (Split-Path $Data) | Out-Null
    Write-Host "Lege isolierten Test-Cluster an ..."
    # `trust` auf localhost: der Cluster hört nur auf 127.0.0.1 (siehe start),
    # ist wegwerfbar und enthält nie echte Daten — ein Passwort wäre hier
    # Zeremonie ohne Schutzwert.
    & $initdb -D $Data -U postgres --auth-local=trust --auth-host=trust -E UTF8 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "initdb fehlgeschlagen." }
}

# Läuft er schon? postmaster.pid heißt: ja.
$running = Test-Path (Join-Path $Data "postmaster.pid")
if (-not $running) {
    Write-Host -NoNewline "Starte PostgreSQL auf $Port "
    # -h 127.0.0.1: nur lokal erreichbar. -F: kein fsync (Testdaten, Tempo).
    & $pg_ctl -D $Data -l $Log -o "-p $Port -h 127.0.0.1 -F" -w start 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Get-Content $Log -Tail 20 -ErrorAction SilentlyContinue
        throw "Server-Start fehlgeschlagen (siehe $Log)."
    }
    Write-Host "ok"
}

# Testdatenbank anlegen, falls sie fehlt (Name trägt 'test' — der zweite
# Riegel in conftest.py).
# Fehlt die DB, gibt psql GAR nichts zurück ($null) — `"$exists"` macht daraus
# einen leeren String, damit .Trim() nicht auf null läuft.
$exists = & $psql -U postgres -h 127.0.0.1 -p $Port -d postgres -tAc `
    "SELECT 1 FROM pg_database WHERE datname='$Db'" 2>$null
if ("$exists".Trim() -ne "1") {
    & $createdb -U postgres -h 127.0.0.1 -p $Port $Db
    if ($LASTEXITCODE -ne 0) { throw "createdb '$Db' fehlgeschlagen." }
}

$env:TEST_DATABASE_URL = "postgresql+psycopg2://postgres@127.0.0.1:$Port/$Db"
Push-Location "$Repo\backend"
try {
    Write-Host "Fahre die Testsuite gegen PostgreSQL ($Db) — ~35 s:"
    & $Py -m pytest tests -q
    $code = $LASTEXITCODE
} finally {
    Pop-Location
    $env:TEST_DATABASE_URL = $null
    if (-not $Keep) { Stop-Cluster }
}

exit $code
