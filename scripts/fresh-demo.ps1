param(
    [Parameter(Mandatory=$true)][string]$Site,
    [string]$Driver = '',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$RunName = 'experiment-v1'
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'use-d-drive.ps1')
$selected = @(Import-Csv (Join-Path $repoRoot 'configs\sites.csv') | Where-Object { $_.site_id -eq $Site })
if ($selected.Count -ne 1) { throw 'Choose exactly one site ID from configs/sites.csv.' }
$collectionPython = Join-Path $repoRoot '.venv\Scripts\python.exe'
$analysisPython = Join-Path $repoRoot '.venv-research\Scripts\python.exe'
$modelPath = Join-Path $repoRoot "models\$RunName\baseline.joblib"
foreach ($required in @($collectionPython, $analysisPython, $modelPath)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required local file missing: $required" }
}
if (-not $Driver) {
    $chrome = Get-Item 'C:\Program Files\Google\Chrome\Application\chrome.exe'
    $major = ([version]$chrome.VersionInfo.ProductVersion).Major
    $cached = @(Get-ChildItem (Join-Path $repoRoot '.cache\selenium\chromedriver') -Recurse -Filter chromedriver.exe |
        Where-Object { ([version]$_.Directory.Name).Major -eq $major } |
        Sort-Object { [version]$_.Directory.Name } -Descending)
    if ($cached.Count -eq 0) { throw 'No compatible cached driver. A D: driver download must be arranged first.' }
    $Driver = $cached[0].FullName
}
if (-not (Test-Path -LiteralPath $Driver)) { throw 'Driver does not exist.' }
# An explicit cached driver prevents Selenium Manager from downloading anything.
$env:SE_OFFLINE = 'true'
$demoId = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') + '-' + [guid]::NewGuid().ToString('N').Substring(0,6)
$demoRoot = Join-Path $repoRoot "data\demo\$demoId"
New-Item -ItemType Directory -Path $demoRoot | Out-Null
$sitesPath = Join-Path $demoRoot 'site.csv'
$selected | Select-Object site_id,url | Export-Csv -Path $sitesPath -NoTypeInformation -Encoding ascii
Push-Location $repoRoot
try {
    & $collectionPython -m peekaboo collect --sites $sitesPath --output $demoRoot --visits 1 --limit 1 --seconds 20 --pause 0 --seed 42 --driver $Driver
    $collectionExit = $LASTEXITCODE
    $sessions = @(Get-ChildItem $demoRoot -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'manifest.jsonl') })
    if ($sessions.Count -ne 1) { throw 'A single completed session manifest was not produced.' }
    & $analysisPython (Join-Path $PSScriptRoot 'predict-demo.py') --session $sessions[0].FullName --model $modelPath
    $predictionExit = $LASTEXITCODE
    if ($collectionExit -ne 0 -or $predictionExit -ne 0) { exit 1 }
} finally {
    Pop-Location
}
