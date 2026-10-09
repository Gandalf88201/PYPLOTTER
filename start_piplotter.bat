@echo off
rem pi-plotter launcher for Windows: double-click this file.
rem First run: creates a private environment in .venv; the modules are installed from the browser page.
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run
set "PY="
if defined PIPLOTTER_PYTHON set "PY=%PIPLOTTER_PYTHON%"
if not defined PY (
  for %%V in (3.13 3.12 3.11 3.10 3.14) do (
    if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V" )
  )
)
if not defined PY ( python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1 && set "PY=python" )
if not defined PY (
  echo pi-plotter: Python 3.10 or newer was not found.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
echo Creating the pi-plotter environment ...
%PY% -m venv .venv
if errorlevel 1 ( echo pi-plotter: could not create .venv & pause & exit /b 1 )
:run
echo Starting pi-plotter - keep this window open; press Ctrl+C to stop.
".venv\Scripts\python.exe" start_piplotter.py %*
if errorlevel 1 pause
