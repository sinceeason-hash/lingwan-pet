$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONIOENCODING = 'utf-8'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $projectPython)) { throw 'Run .\setup.ps1 first.' }
# Read the Unicode application name from the UTF-8 Python source for PowerShell 5 compatibility.
$source = [System.IO.File]::ReadAllText((Join-Path $PSScriptRoot 'pet.py'), [System.Text.Encoding]::UTF8)
$appName = [regex]::Match($source, '(?m)^APP_NAME = "([^"]+)"').Groups[1].Value
if (!$appName) { throw 'Application name was not found.' }
& $projectPython -m PyInstaller --noconfirm --onefile --windowed --name $appName --icon 'assets\pet.ico' --add-data 'assets\character.png;assets' --add-data 'assets\run_*.png;assets' --add-data 'assets\pet.ico;assets' --distpath 'delivery' --workpath 'build' --specpath '.' --exclude-module tkinter --exclude-module numpy --exclude-module PIL --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets pet.py
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
Write-Host ('EXE: ' + (Join-Path $PSScriptRoot ('delivery\' + $appName + '.exe')))
