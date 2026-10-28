param([int]$Visits = 2, [int]$Seconds = 20, [int]$Limit = 3)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $pythonPath = Join-Path $repoRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Create .venv and install Selenium first; see docs/dataset.md.'
    }
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    $env:SE_CACHE_PATH = Join-Path $repoRoot '.cache/selenium'
    $env:SE_AVOID_STATS = 'true'
    & $pythonPath -m peekaboo doctor
    & $pythonPath -m peekaboo collect --limit $Limit --visits $Visits --seconds $Seconds --pause 10
    $collectionExit = $LASTEXITCODE
    if ($collectionExit -ne 0) {
        throw 'Pilot incomplete: review the latest data/raw session manifest and logs.'
    }
    Write-Host 'Pilot finished. Review screenshots before accepting any candidate trace.'
} finally {
    Pop-Location
}
