@echo off
REM ============================================================
REM TITAN XAU AI — Windows MT5 Acquisition Launcher
REM ============================================================
REM Double-click this file to run the acquisition script.
REM ============================================================

echo.
echo ============================================================
echo  TITAN XAU AI - Windows MT5 Acquisition Launcher
echo ============================================================
echo.

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo         Download from: https://www.python.org/downloads/
    echo         During install, check "Add Python to PATH".
    pause
    exit /b 1
)

REM Check MetaTrader5 package is installed
python -c "import MetaTrader5" >nul 2>&1
if errorlevel 1 (
    echo [SETUP] Installing required packages ...
    echo.
    pip install MetaTrader5 pandas pyarrow
    if errorlevel 1 (
        echo [ERROR] Failed to install packages.
        pause
        exit /b 1
    )
    echo.
    echo [OK] Packages installed.
    echo.
)

REM Check MT5 terminal is running (basic check)
tasklist /FI "IMAGENAME eq terminal64.exe" 2>NUL | find /I "terminal64.exe" >NUL
if errorlevel 1 (
    echo [WARNING] MT5 terminal (terminal64.exe) does not appear to be running.
    echo           Please open MetaTrader 5 terminal and login to Exness account
    echo           before continuing.
    echo.
    pause
)

echo [START] Running acquisition script ...
echo.

python "%~dp0titan_mt5_acquire.py"

echo.
echo ============================================================
echo  Script finished. Output in: %~dp0titan_mt5_data\
echo ============================================================
echo.
echo Next step: ZIP the titan_mt5_data folder and share it back.
echo.
pause
