@echo off
setlocal
rem The project folder becomes the working directory for cache and imports.
pushd "%~dp0"
if errorlevel 1 (
    echo Cannot open the project folder.
    pause
    exit /b 1
)
rem A virtual environment keeps project packages separate from other Python apps.
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 (
        echo Python 3.11 is required. Install it and try again.
        pause
        exit /b 1
    )
)
rem Download the versions listed in requirements.txt, then launch the source code.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Package installation failed. Check the internet connection.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py
if errorlevel 1 pause
popd
