@echo off
REM ============================================================
REM  TITAN XAU AI - First-Run Wizard (Sprint 9.9.3.40)
REM  Windows-friendly safe first-run check for non-technical operators
REM  ============================================================
REM  NEVER enables live trading.
REM  NEVER exposes market execution.
REM  NEVER exposes DEMO_MICRO_EXECUTE.
REM  NEVER imports MetaTrader5.
REM  NEVER sends orders.
REM  NEVER asks for account password.
REM  NEVER asks for API key.
REM ============================================================

setlocal

REM ─── TITAN home ──
set TITAN_HOME=%~dp0
cd /d "%TITAN_HOME%"

REM ─── Activate virtual environment if available ──
if exist "%TITAN_HOME%venv\Scripts\activate.bat" (
    call "%TITAN_HOME%venv\Scripts\activate.bat"
) else if exist "%TITAN_HOME%.venv\Scripts\activate.bat" (
    call "%TITAN_HOME%.venv\Scripts\activate.bat"
) else if exist "%TITAN_HOME%env\Scripts\activate.bat" (
    call "%TITAN_HOME%env\Scripts\activate.bat"
)

REM ─── Verify Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH.
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM ─── PYTHONPATH ──
set PYTHONPATH=%TITAN_HOME%

echo.
echo ============================================================
echo  TITAN XAU AI - First-Run Wizard
echo  Sprint 9.9.3.40
echo ============================================================
echo  Live trading : BLOCKED
echo  Market exec  : NOT AVAILABLE from this wizard
echo  MetaTrader5  : NOT IMPORTED by this wizard
echo  Credentials  : NOT REQUESTED by this wizard
echo ============================================================
echo.

REM ─── Run first-run wizard ──
python "%TITAN_HOME%scripts\operator\titan_first_run.py"

echo.
pause
endlocal
exit /b 0
