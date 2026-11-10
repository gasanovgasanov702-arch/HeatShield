@echo off
setlocal
rem Prefer the latest v0.2.0 build so an older EXE in dist\HeatShield cannot be opened accidentally.
if exist "%~dp0dist\HeatShield-v0.2.0\HeatShield\HeatShield.exe" (
    start "" "%~dp0dist\HeatShield-v0.2.0\HeatShield\HeatShield.exe"
    exit /b 0
)
rem Keep the previous build as a fallback when the new release folder is not unpacked yet.
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
