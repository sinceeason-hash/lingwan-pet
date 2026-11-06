@echo off
rem One-click pet character swap. Drag an image onto this file,
rem or double-click to pick an image from a dialog.
setlocal
set "DIR=%~dp0"
if exist "%DIR%.venv\Scripts\python.exe" (
    set "PY=%DIR%.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"%PY%" "%DIR%tools\swap_character.py" %*
if errorlevel 1 pause
