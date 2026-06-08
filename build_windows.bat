@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Spillway Workbench - Builder

echo.
echo ============================================================
echo   Spillway Workbench - Windows .exe Builder v1.0
echo ============================================================
echo.
echo   This script will build SpillwayWorkbench.exe on this PC.
echo   Estimated time: 5-10 minutes on first run.
echo.

REM ---- Step 1: Find Python ----
echo [1/5] Looking for Python...
set PYTHON_EXE=
where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_EXE=python
    goto :found_python
)
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set PYTHON_EXE=py -3
    goto :found_python
)

echo.
echo   *** Python is not installed or not in your PATH. ***
echo.
echo   Please install Python 3.11 or newer:
echo   1. Go to https://www.python.org/downloads/windows/
echo   2. Click the big yellow "Download Python 3.11.x" button
echo   3. Run the installer
echo   4. *** IMPORTANT *** On the first screen, check the box
echo      at the bottom that says "Add Python to PATH"
echo   5. Click "Install Now"
echo   6. After install completes, run this script again
echo.
echo   Press any key to open the Python download page...
pause >nul
start https://www.python.org/downloads/windows/
exit /b 1

:found_python
%PYTHON_EXE% --version
echo   Found Python.
echo.

REM ---- Step 2: Verify we have the swb source ----
echo [2/5] Checking source files...
if not exist "swb.spec" (
    if not exist "ui\mdi_main.py" (
        echo.
        echo   *** Source files not found! ***
        echo.
        echo   This script must be run from inside the SWB_v1_source
        echo   folder. The folder should contain:
        echo     - swb.spec
        echo     - app_state.py
        echo     - cavicuspill\
        echo     - em_py\
        echo     - ui\
        echo.
        echo   You should have extracted SWB_v1_source.zip and run this
        echo   script from the resulting folder.
        echo.
        pause
        exit /b 1
    )
)
echo   Source files found.
echo.

REM ---- Step 3: Install required packages ----
echo [3/5] Installing required packages...
echo   (PySide6, numpy, matplotlib, pyinstaller)
echo   This may take 3-5 minutes on first run.
echo.

%PYTHON_EXE% -m pip install --upgrade pip --quiet --disable-pip-version-check 2>nul
%PYTHON_EXE% -m pip install --quiet --disable-pip-version-check PySide6 numpy matplotlib pyinstaller
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   *** Package installation failed. ***
    echo   Possible causes:
    echo     - No internet connection
    echo     - Corporate firewall blocking pip
    echo     - Python is too old
    echo.
    echo   Try running this script as Administrator (right-click -^> Run as administrator)
    echo   Or check your internet connection.
    echo.
    pause
    exit /b 1
)
echo   Packages installed successfully.
echo.

REM ---- Step 4: Build the .exe ----
echo [4/5] Building SpillwayWorkbench.exe...
echo   This takes 1-3 minutes. Please wait.
echo.

if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build

%PYTHON_EXE% -m PyInstaller swb.spec --noconfirm --clean
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo   *** Build failed. ***
    echo.
    echo   Common causes:
    echo     - Antivirus software blocking PyInstaller
    echo       (Try temporarily disabling real-time protection)
    echo     - Not enough disk space (need ~2 GB free)
    echo     - The build log is in build\SpillwayWorkbench\warn-SpillwayWorkbench.txt
    echo.
    echo   Try disabling antivirus, then run this script again.
    echo.
    pause
    exit /b 1
)

REM ---- Step 5: Verify and report ----
echo [5/5] Verifying build...
echo.

if not exist "dist\SpillwayWorkbench.exe" (
    echo   *** ERROR: dist\SpillwayWorkbench.exe was not created. ***
    echo   Please report this to the developer with the build log.
    pause
    exit /b 1
)

for %%A in (dist\SpillwayWorkbench.exe) do set SIZE=%%~zA
set /a SIZEMB=%SIZE% / 1048576
set /a SIZEMB10=%SIZE% * 10 / 1048576

echo.
echo ============================================================
echo   SUCCESS!
echo ============================================================
echo.
echo   Your .exe is at:
echo     %CD%\dist\SpillwayWorkbench.exe
echo.
echo   Size: %SIZEMB% MB
echo.
echo   You can now:
echo     - Double-click it to run
echo     - Copy it to your Desktop
echo     - Email it to colleagues
echo     - Put it on a USB drive
echo.
echo   The .exe is fully standalone. It does NOT need Python or
echo   any other software. It will run on any Windows 10 or 11 PC.
echo.
echo   Press any key to open the folder containing the .exe...
pause >nul
explorer dist

endlocal
