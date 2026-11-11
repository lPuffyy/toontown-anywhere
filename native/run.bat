@echo off
rem Runs the native client from this folder (sets up its own Python environment the first time).
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -m venv .venv || goto :fail
  .venv\Scripts\pip install -r requirements.txt || goto :fail
)
.venv\Scripts\python -m tta_native %*
exit /b %errorlevel%
:fail
echo Setup failed. Install Python 3.9 or newer from python.org and run this again.
pause
