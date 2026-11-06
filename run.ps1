$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { throw 'Run .\setup.ps1 first.' }
& $projectPython (Join-Path $PSScriptRoot 'pet.py')
if ($LASTEXITCODE -ne 0) { throw 'Application exited with an error.' }
