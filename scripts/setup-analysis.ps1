param([string]$Python = '')
. (Join-Path $PSScriptRoot 'use-d-drive.ps1')
$analysisPython = Join-Path $repoRoot '.venv-research\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $analysisPython)) {
    if (-not $Python) {
        $Python = Join-Path $repoRoot '.venv\Scripts\python.exe'
        if (-not (Test-Path -LiteralPath $Python)) {
            if (Get-Command py -ErrorAction SilentlyContinue) {
                $Python = & py -3.13 -c 'import sys; print(sys.executable)'
            } elseif (Get-Command python -ErrorAction SilentlyContinue) {
                $Python = (Get-Command python).Source
            } else {
                throw 'Python 3.13 is required. Pass -Python with its executable path.'
            }
        }
    }
    & $Python -c 'import sys; assert sys.version_info[:2] == (3, 13), "Use Python 3.13 for the frozen baseline model"'
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & $Python -m venv (Join-Path $repoRoot '.venv-research')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $analysisPython -m pip install --disable-pip-version-check --no-compile --only-binary=:all: -r (Join-Path $repoRoot 'requirements-research-lock.txt')
exit $LASTEXITCODE
