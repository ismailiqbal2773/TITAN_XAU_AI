@echo off
REM ============================================================
REM  TITAN XAU AI — Build TITAN.exe (Sprint 7.5)
REM  ============================================================
REM  This script builds a Windows executable using PyInstaller.
REM
REM  Prerequisites:
REM    - Python 3.12+ installed
REM    - pip install pyinstaller
REM    - All TITAN dependencies installed
REM
REM  Output:
REM    dist\TITAN.exe  (single executable)
REM
REM  Usage:
REM    Double-click build_titan.bat, OR:
REM    build_titan.bat
REM ============================================================

setlocal

set TITAN_HOME=%~dp0
cd /d "%TITAN_HOME%"

echo ============================================================
echo  TITAN XAU AI — Building TITAN.exe
echo ============================================================
echo.

REM ─── Verify Python ──
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

REM ─── Verify PyInstaller ──
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM ─── Clean previous builds ──
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo.

REM ─── Build ──
echo Building TITAN.exe...
echo This may take 5-10 minutes...
echo.
pyinstaller TITAN.spec --noconfirm

if errorlevel 1 (
    echo.
    echo ============================================================
    echo  BUILD FAILED
    echo  Check the error messages above
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  BUILD SUCCESSFUL
echo ============================================================
echo  Executable: dist\TITAN.exe
echo  Size:
dir /b dist\TITAN.exe
for %%I in (dist\TITAN.exe) do echo    %%~zI bytes
echo.
echo  To distribute:
echo  1. Copy dist\TITAN.exe to target machine
echo  2. Run TITAN.exe (no Python required)
echo  3. Follow the Setup Wizard prompts
echo ============================================================
pause
endlocal
