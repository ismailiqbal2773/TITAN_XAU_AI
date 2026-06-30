@echo off
REM ============================================================
REM  TITAN XAU AI - Operator Console (Sprint 9.9.3.35)
REM  Windows-friendly safe RC command center
REM  ============================================================
REM  NEVER enables live trading.
REM  NEVER exposes market execution.
REM  NEVER exposes DEMO_MICRO_EXECUTE.
REM  NEVER imports MetaTrader5.
REM  NEVER sends orders.
REM ============================================================

setlocal EnableDelayedExpansion

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
    echo Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

REM ─── PYTHONPATH ──
set PYTHONPATH=%TITAN_HOME%

:MENU
cls
echo.
echo ============================================================
echo  TITAN XAU AI - Operator Console
echo  Sprint 9.9.3.35
echo ============================================================
echo  Live trading : BLOCKED
echo  Market exec  : NOT AVAILABLE from this console
echo  MetaTrader5  : NOT IMPORTED by this console
echo ============================================================
echo.
echo   1  STATUS
echo   2  RC CHECK
echo   3  SAFETY CHECK
echo   4  BROKER STATUS
echo   5  FULL AUDIT
echo   6  HELP
echo   0  EXIT
echo.
set /p CHOICE="Select option (0-6): "

if "%CHOICE%"=="1" goto STATUS
if "%CHOICE%"=="2" goto RCCHECK
if "%CHOICE%"=="3" goto SAFETYCHECK
if "%CHOICE%"=="4" goto BROKERSTATUS
if "%CHOICE%"=="5" goto FULLAUDIT
if "%CHOICE%"=="6" goto HELP
if "%CHOICE%"=="0" goto END
echo Invalid choice.
pause
goto MENU

:STATUS
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" status
pause
goto MENU

:RCCHECK
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" rc-check
pause
goto MENU

:SAFETYCHECK
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" safety-check
pause
goto MENU

:BROKERSTATUS
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" broker-status
pause
goto MENU

:FULLAUDIT
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" full-audit
pause
goto MENU

:HELP
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" help
pause
goto MENU

:END
endlocal
exit /b 0
