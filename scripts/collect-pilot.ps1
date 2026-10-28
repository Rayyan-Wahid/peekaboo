param([int]$Visits = 2, [int]$Seconds = 20, [int]$Limit = 3,
      [string]$Sites = 'configs/sites.csv')
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
    & $pythonPath -m peekaboo collect --sites $Sites --limit $Limit --visits $Visits --seconds $Seconds --pause 10
    $collectionExit = $LASTEXITCODE
    if ($collectionExit -ne 0) {
        Write-Warning 'Some visits failed or need review. Saved captures are retained; inspect the latest session manifest and logs.'
    } else {
        Write-Host 'Pilot finished. Review screenshots before accepting any candidate trace.'
    }
} finally {
    Pop-Location
}
