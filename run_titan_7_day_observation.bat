@echo off
REM ============================================================
REM  TITAN XAU AI - 7-Day Observation Helper (Sprint 9.9.3.42)
REM  Windows-friendly controlled 7-day demo observation menu
REM  ============================================================
REM  NEVER enables live trading.
REM  NEVER exposes market execution.
REM  NEVER exposes DEMO_MICRO_EXECUTE.
REM  NEVER exposes raw_mt5_probe.
REM  NEVER exposes repeatability execution.
REM  NEVER exposes order_send.
REM  NEVER exposes retraining/HPO.
REM  NEVER imports MetaTrader5.
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
    echo Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

REM ─── PYTHONPATH ──
set PYTHONPATH=%TITAN_HOME%

:MENU
cls
echo.
echo ============================================================
echo  TITAN XAU AI - 7-Day Observation Helper
echo  Sprint 9.9.3.42
echo ============================================================
echo  Live trading : BLOCKED
echo  Market exec  : NOT AVAILABLE from this helper
echo  MetaTrader5  : NOT IMPORTED by this helper
echo  Broker       : MetaQuotes-Demo only for current observation
echo ============================================================
echo.
echo   1  START 7-DAY OBSERVATION CHECK
echo   2  RUN DAILY SCORECARD
echo   3  FINALIZE 7-DAY REPORT
echo   4  OPEN OPERATOR CONSOLE
echo   0  EXIT
echo.
set /p CHOICE="Select option (0-4): "

if "%CHOICE%"=="1" goto STARTCHECK
if "%CHOICE%"=="2" goto DAILYSCORECARD
if "%CHOICE%"=="3" goto FINALIZE
if "%CHOICE%"=="4" goto OPERATORCONSOLE
if "%CHOICE%"=="0" goto END
echo Invalid choice.
pause
goto MENU

:STARTCHECK
cls
python "%TITAN_HOME%scripts\operator\start_7_day_demo_observation.py" --check-only
pause
goto MENU

:DAILYSCORECARD
cls
echo.
set /p DAYNUM="Enter day number (1-7): "
python "%TITAN_HOME%scripts\operator\run_daily_observation_scorecard.py" --day %DAYNUM% --since-hours 24
pause
goto MENU

:FINALIZE
cls
python "%TITAN_HOME%scripts\operator\finalize_7_day_demo_observation.py"
pause
goto MENU

:OPERATORCONSOLE
cls
python "%TITAN_HOME%scripts\operator\titan_operator.py" help
echo.
echo To use the full operator console menu, run:
echo   run_titan_operator.bat
pause
goto MENU

:END
endlocal
exit /b 0
