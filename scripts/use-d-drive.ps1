# Dot-source from PowerShell: . .\scripts\use-d-drive.ps1
$repoRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($repoRoot) -ne 'D:\') {
    throw 'This launcher requires the project on D:.'
}
$cacheRoot = Join-Path $repoRoot '.cache'
foreach ($name in @('tmp', 'pip', 'matplotlib', 'joblib', 'wireshark', 'streamlit', 'selenium', 'sklearn')) {
    New-Item -ItemType Directory -Force -Path (Join-Path $cacheRoot $name) | Out-Null
}
$env:TEMP = Join-Path $cacheRoot 'tmp'
$env:TMP = $env:TEMP
$env:TMPDIR = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $cacheRoot 'pip'
$env:UV_CACHE_DIR = Join-Path $cacheRoot 'uv'
$env:XDG_CACHE_HOME = $cacheRoot
$env:MPLCONFIGDIR = Join-Path $cacheRoot 'matplotlib'
$env:JOBLIB_TEMP_FOLDER = Join-Path $cacheRoot 'joblib'
$env:WIRESHARK_CONFIG_DIR = Join-Path $cacheRoot 'wireshark'
$env:STREAMLIT_HOME = Join-Path $cacheRoot 'streamlit'
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = 'false'
$env:SE_CACHE_PATH = Join-Path $cacheRoot 'selenium'
$env:SE_AVOID_STATS = 'true'
$env:SCIKIT_LEARN_DATA = Join-Path $cacheRoot 'sklearn'
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path $repoRoot 'src'
