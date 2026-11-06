. (Join-Path $PSScriptRoot 'use-d-drive.ps1')
& (Join-Path $repoRoot '.venv-research\Scripts\python.exe') (Join-Path $PSScriptRoot 'start-dashboard.py')
exit $LASTEXITCODE
