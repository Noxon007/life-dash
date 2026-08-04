# Löscht die Versionsspuren von vor der Veröffentlichung: Git-Tags, GitHub-
# Releases und ghcr-Image-Versionen. Behalten wird genau ein Stand.
#
# WARUM ES DIESES SKRIPT GIBT (Entscheidung 2026-08-04, siehe
# docs/internal/ROADMAP.md §5): 49 Tags auf 154 Commits, angefangen bei v0.1 —
# entstanden, weil ein SemVer-Tag lange der einzige Weg war, ein Image auf den
# eigenen Server zu bekommen. Seit dem Zwei-Gleise-Modell baut jeder Push auf
# `main` ein `:main`-Image, und eine Versionsnummer entsteht nur noch, wenn ein
# NUTZER einen Unterschied merkt.
#
# Keines der alten Images ist installierbar: der getestete Upgrade-Pfad ist
# R1(f) und existiert noch nicht. Was ein Fremder bei 1.0 sieht, ist die
# Releases-Seite und die ghcr-Paketliste — und die sollen nicht bei v0.1
# anfangen.
#
# NICHTS GEHT DABEI VERLOREN. Der Nachweis waren nie die Tags:
#   - was gebaut wurde, in welcher Version  -> DECISIONS.md Anhang A
#   - warum                                 -> DECISIONS.md, nummeriert
#   - was ein Nutzer merkte                 -> CHANGELOG.md
#   - die Commits selbst                    -> unberührt (28 MB Historie;
#                                              DECISIONS.md zitiert Hashes)
#
# WANN AUSFÜHREN: unmittelbar vor 1.0, nicht heute. Es ist der einzige
# unumkehrbare Schritt des ganzen Aufräumens, und bis dahin kostet Warten
# nichts.
#
#   pwsh tools/cleanup-old-versions.ps1              # zeigt nur, was passieren würde
#   pwsh tools/cleanup-old-versions.ps1 -Execute     # führt aus

[CmdletBinding()]
param(
    # Der eine Stand, der stehen bleibt. Vor 1.0 ist das die letzte 0.x.
    [string] $Keep = 'v0.39.0',
    # Ohne diesen Schalter wird nichts gelöscht, nur aufgelistet.
    [switch] $Execute
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $repoRoot

$remoteUrl = git remote get-url origin
if ($remoteUrl -notmatch '[:/]([^/]+)/([^/]+?)(\.git)?$') {
    throw "Repo-Pfad nicht aus der Remote-URL lesbar: $remoteUrl"
}
$owner = $Matches[1]
$repo  = $Matches[2]
$pkg   = $repo.ToLowerInvariant()   # ghcr-Paketnamen sind kleingeschrieben

$tags = @(git tag -l | Where-Object { $_ -ne $Keep })

Write-Host ""
Write-Host "Repo   : $owner/$repo" -ForegroundColor Cyan
Write-Host "Behalte: $Keep" -ForegroundColor Cyan
Write-Host "Lösche : $($tags.Count) Tags" -ForegroundColor Cyan
Write-Host ""

if (-not $Execute) {
    Write-Host "TROCKENLAUF — es wird nichts gelöscht. Mit -Execute ausführen." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Betroffene Tags:"
    $tags | ForEach-Object { "  $_" }
    Write-Host ""
}

# --------------------------------------------------------------------------- #
# 1) Git-Tags — lokal und auf dem Server
#
# Getrennt und in dieser Reihenfolge: erst der Server, dann lokal. Bricht es in
# der Mitte ab, ist der lokale Stand noch die vollständige Liste und ein zweiter
# Lauf holt den Rest nach. Andersherum wüsste niemand mehr, was fehlt.
# --------------------------------------------------------------------------- #
if ($Execute -and $tags.Count -gt 0) {
    Write-Host "[1/3] Tags auf origin löschen …" -ForegroundColor Green
    # In Blöcken statt 48 Einzelaufrufe — ein Push je Block.
    for ($i = 0; $i -lt $tags.Count; $i += 20) {
        $chunk = $tags[$i..([Math]::Min($i + 19, $tags.Count - 1))]
        $refs  = $chunk | ForEach-Object { ":refs/tags/$_" }
        git push origin @refs
    }

    Write-Host "[2/3] Tags lokal löschen …" -ForegroundColor Green
    git tag -d @tags | Out-Null
}

# --------------------------------------------------------------------------- #
# 2) GitHub-Releases
#
# Ein gelöschter Tag räumt SEIN RELEASE NICHT MIT WEG — das Release bleibt als
# „Draft ohne Tag" auf der Releases-Seite stehen, also genau dort, wo der
# Fremde hinsieht. Deshalb ein eigener Schritt.
# --------------------------------------------------------------------------- #
$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($Execute -and $tags.Count -gt 0) {
    if ($gh) {
        Write-Host "[3/3] GitHub-Releases löschen …" -ForegroundColor Green
        $existing = (gh release list --repo "$owner/$repo" --limit 200 --json tagName |
                     ConvertFrom-Json).tagName
        foreach ($t in $tags) {
            if ($existing -contains $t) {
                gh release delete $t --repo "$owner/$repo" --yes
                Write-Host "  gelöscht: $t"
            }
        }
    } else {
        Write-Host "[3/3] ÜBERSPRUNGEN — gh CLI nicht installiert." -ForegroundColor Yellow
        Write-Host "      Entweder 'winget install GitHub.cli' und dieses Skript erneut,"
        Write-Host "      oder von Hand: https://github.com/$owner/$repo/releases"
    }
}

# --------------------------------------------------------------------------- #
# 3) ghcr-Image-Versionen
#
# Die dritte, unabhängige Liste. Ein gelöschter Tag löscht kein Image; das
# Image ist eine Paketversion unter github.com/users/<owner>/packages.
#
# BEWUSST NICHT AUTOMATISIERT. Der Aufruf ist ein DELETE auf die Packages-API
# und braucht ein Token mit `delete:packages` — ein Recht, das man für einen
# einmaligen Aufräumlauf nicht verteilt, und ein Skript, das Paketversionen
# nach Nummernmuster löscht, ist die falsche Sorte Werkzeug für einen Schritt,
# den man genau einmal macht. Die Weboberfläche zeigt zu jeder Version, welche
# Tags daran hängen — das will man hier sehen.
#
# `latest` und `main` müssen stehen bleiben: `latest` ist das, was ein
# `docker compose up` ohne Version zieht, `main` ist das Testgleis.
# --------------------------------------------------------------------------- #
Write-Host ""
Write-Host "Noch von Hand — die ghcr-Images:" -ForegroundColor Cyan
Write-Host "  https://github.com/users/$owner/packages/container/$pkg/versions"
Write-Host "  Alles außer den Versionen löschen, an denen 'latest', 'main' oder"
Write-Host "  '$($Keep.TrimStart('v'))' hängt."
Write-Host ""

if ($Execute) {
    Write-Host "Fertig. Kontrolle:" -ForegroundColor Green
    Write-Host "  git tag -l                 (sollte nur $Keep zeigen)"
    Write-Host "  git ls-remote --tags origin"
} else {
    Write-Host "Nochmal mit -Execute, wenn es so stimmt." -ForegroundColor Yellow
}
