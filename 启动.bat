@echo off
rem LeapR launcher
rem Prefer the packaged exe. Fall back to running from source with a console,
rem so any error is visible instead of silently vanishing (pythonw hides it).
cd /d "%~dp0"

if exist "dist\LeapR\LeapR.exe" (
    start "" "dist\LeapR\LeapR.exe"
    exit /b
)

if exist ".venv\Scripts\python.exe" (
    echo [LeapR] no packaged exe found, running from source...
    ".venv\Scripts\python.exe" "main.py"
    exit /b
)

echo [LeapR] cannot find LeapR.exe or .venv
echo         build it first:  .venv\Scripts\python.exe tools\build_exe.py
pause
