@echo off
REM Windows launcher: creates a virtual environment on first run, installs packages, starts the app.
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 ( set PY=py -3 ) else ( set PY=python )
if not exist .venv (
    echo Creating virtual environment...
    %PY% -m venv .venv || goto :fail
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r requirements.txt || goto :fail
) else (
    call .venv\Scripts\activate.bat
)
python run.py %*
pause
exit /b 0
:fail
echo.
echo Setup failed. Make sure Python 3.10 or newer is installed (python.org) and "Add to PATH" was ticked.
pause
exit /b 1
