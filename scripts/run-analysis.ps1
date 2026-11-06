param([ValidateSet('extract','experiment','all')][string]$Stage = 'all',
      [string]$RunName = 'experiment-v1')
. (Join-Path $PSScriptRoot 'use-d-drive.ps1')
$pythonPath = Join-Path $repoRoot '.venv-research\Scripts\python.exe'
if ($Stage -in @('extract','all')) {
    & $pythonPath -m peekaboo extract --root $repoRoot
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
if ($Stage -in @('experiment','all')) {
    & $pythonPath -m peekaboo experiment --root $repoRoot --run-name $RunName
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
