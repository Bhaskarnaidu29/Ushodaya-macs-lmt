@echo off
REM ============================================================
REM  UDLMS - Build Script  (v2)
REM  Ushodaya MACS Ltd Loan Management System
REM
REM  HOW TO USE:
REM  1. Place this file and udlms.spec in the same folder as App.py
REM  2. Double-click build_exe.bat  (or run from Command Prompt)
REM  3. Wait 3-8 minutes
REM  4. EXE will be in:  dist\UDLMS.exe
REM ============================================================

title UDLMS Build Tool
cd /d "%~dp0"

echo.
echo ============================================================
echo   UDLMS EXE Builder v2
echo   Building from: %CD%
echo ============================================================
echo.

REM ---- Verify correct directory ------------------------------
if not exist "App.py" (
    echo [ERROR] App.py not found in: %CD%
    echo         Make sure build_exe.bat is in the SAME folder as App.py.
    pause
    exit /b 1
)
if not exist "run_lms.py" (
    echo [ERROR] run_lms.py not found in: %CD%
    pause
    exit /b 1
)
if not exist "udlms.spec" (
    echo [ERROR] udlms.spec not found in: %CD%
    echo         Copy udlms.spec into this folder and try again.
    pause
    exit /b 1
)
echo [OK] Project folder verified: %CD%

REM ---- Check Python ------------------------------------------
echo.
echo [1/5] Checking Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo        %%v
echo [OK]

REM ---- Upgrade pip -------------------------------------------
echo.
echo [2/5] Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK]

REM ---- Install PyInstaller -----------------------------------
echo.
echo [3/5] Installing PyInstaller...
pip install pyinstaller --upgrade --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Could not install PyInstaller.
    pause
    exit /b 1
)
echo [OK]

REM ---- Install project dependencies --------------------------
echo.
echo [4/5] Installing dependencies...
if exist "requirements.txt" (
    pip install -r requirements.txt --quiet
) else (
    echo        requirements.txt not found - installing core packages...
    pip install flask pyodbc pandas openpyxl reportlab python-dotenv werkzeug --quiet
)
if %errorlevel% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)
echo [OK]

REM ---- Show bundle status ------------------------------------
echo.
echo [INFO] Checking folders...
if exist "templates" (echo        templates\  FOUND) else (echo [WARN] templates\  NOT FOUND - pages will not render!)
if exist "static"    (echo        static\     FOUND) else (echo [WARN] static\     NOT FOUND - CSS/JS missing)
if exist ".env"      (echo        .env        FOUND) else (echo [WARN] .env        NOT FOUND - add manually to dist\)

REM ---- Run PyInstaller ----------------------------------------
echo.
echo [5/5] Building EXE (3-8 mins)...
echo.

pyinstaller udlms.spec --clean --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo ============================================================
    echo   BUILD FAILED  -  read the errors above
    echo ============================================================
    echo.
    echo   Common fixes:
    echo   1. Missing package    -^>  pip install ^<package^>
    echo   2. Missing templates\ -^>  put HTML files in templates\ folder
    echo   3. Import error       -^>  python App.py  to see the error
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   BUILD SUCCESSFUL!
echo   EXE:  %CD%\dist\UDLMS.exe
echo ============================================================
echo.
echo   Next: copy .env into dist\  before distributing.
echo.
explorer "%CD%\dist"
pause
exit /b 0
