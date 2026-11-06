param([string]$PythonExe = 'python', [string]$IndexUrl = 'https://pypi.org/simple')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
& $PythonExe -c 'import sys; assert (3, 10) <= sys.version_info[:2] <= (3, 13), "Use Python 3.10-3.13 (3.12 recommended)"; assert sys.maxsize > 2**32, "64-bit Python is required"; print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'A 64-bit Python 3.10-3.13 installation is required.' }
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) {
    & $PythonExe -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Project environment creation failed.' }
}
& $projectPython -m pip install --disable-pip-version-check --index-url $IndexUrl -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
Write-Host 'Ready. Run .\run.ps1 or .\build.ps1.'
