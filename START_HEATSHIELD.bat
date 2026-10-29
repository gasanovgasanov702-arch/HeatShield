@echo off
setlocal
rem This file opens the ready-to-use build first.
if exist "%~dp0dist\HeatShield\HeatShield.exe" (
    start "" "%~dp0dist\HeatShield\HeatShield.exe"
    exit /b 0
)
rem The same file also works inside the dist\HeatShield folder.
if exist "%~dp0HeatShield.exe" (
    start "" "%~dp0HeatShield.exe"
    exit /b 0
)
rem If no EXE exists, run the already installed Python environment.
if exist "%~dp0.venv\Scripts\python.exe" (
    pushd "%~dp0"
    if errorlevel 1 exit /b 1
    ".venv\Scripts\python.exe" main.py
    if errorlevel 1 (
        echo HeatShield failed. Read the error above.
        pause
        exit /b 1
    )
    popd
    exit /b 0
)
echo HeatShield was not found. Run SETUP_AND_RUN.bat first.
pause
exit /b 1
