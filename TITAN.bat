@echo off
REM ============================================================
REM  TITAN XAU AI — Windows One-Click Launcher (Sprint 5)
REM  ============================================================
REM  DEFAULT: dry_run mode (NO real orders)
REM
REM  To enable LIVE trading:
REM    1. Edit config\runtime.yaml → dry_run: false, live_trading: true
REM    2. Set environment variable: set TITAN_LIVE_TRADING=1
REM    3. Re-run this script
REM
REM  Otherwise the system will fail-closed.
REM ============================================================

setlocal EnableDelayedExpansion

REM ─── Configuration ──
set TITAN_HOME=%~dp0
set TITAN_CONFIG=%TITAN_HOME%config\runtime.yaml
set TITAN_PYTHON=python
set TITAN_LOG_DIR=%TITAN_HOME%logs
set TITAN_LOG_FILE=%TITAN_LOG_DIR%\titan_%DATE:~-4,4%%DATE:~-7,2%%DATE:~-10,2%_%TIME:~0,2%%TIME:~3,2%.log

REM ─── Safety: refuse to start if TITAN_LIVE_TRADING is set without confirmation ──
if "%TITAN_LIVE_TRADING%"=="1" (
    echo.
    echo ============================================================
    echo  WARNING: TITAN_LIVE_TRADING=1 detected
    echo  This will ENABLE LIVE ORDER SUBMISSION
    echo ============================================================
    echo.
    set /p CONFIRM="Type 'YES I UNDERSTAND' to continue: "
    if not "!CONFIRM!"=="YES I UNDERSTAND" (
        echo Aborting: confirmation not received
        exit /b 1
    )
)

REM ─── Verify Python ──
%TITAN_PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

REM ─── Verify config exists ──
if not exist "%TITAN_CONFIG%" (
    echo ERROR: Config file not found: %TITAN_CONFIG%
    pause
    exit /b 1
)

REM ─── Create log directory ──
if not exist "%TITAN_LOG_DIR%" mkdir "%TITAN_LOG_DIR%"

REM ─── Set PYTHONPATH ──
set PYTHONPATH=%TITAN_HOME%

REM ─── Print banner ──
echo.
echo ============================================================
echo  TITAN XAU AI — Starting
echo ============================================================
echo  Home:     %TITAN_HOME%
echo  Config:   %TITAN_CONFIG%
echo  Log:      %TITAN_LOG_FILE%
echo  Mode:     dry_run ^(default — no real orders^)
echo  Live:     %TITAN_LIVE_TRADING%
echo ============================================================
echo.

REM ─── Run launcher ──
cd /d "%TITAN_HOME%"
%TITAN_PYTHON% -m titan.runtime.launcher --config "%TITAN_CONFIG%" 2>&1 | tee "%TITAN_LOG_FILE%"

REM ─── Exit code handling ──
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  TITAN exited with error code %errorlevel%
    echo  Check log: %TITAN_LOG_FILE%
    echo ============================================================
    pause
    exit /b %errorlevel%
)

echo.
echo ============================================================
echo  TITAN completed successfully
echo ============================================================
pause
endlocal
