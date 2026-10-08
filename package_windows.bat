@echo off
REM Telegram Auto Download Bot - Complete Windows Package Builder
REM Builds the executable with PyInstaller, then the installer with Inno Setup.
REM Any failing step stops the build immediately.

setlocal

echo ====================================
echo Telegram Auto Download Bot
echo Complete Windows Package Builder
echo ====================================
echo.

set "START_TIME=%TIME%"
set "ERROR_OCCURRED=0"

REM ===== Version constant =====
set "APP_VERSION=2.5.0"
REM ============================

set "EXE_PATH=dist\TelegramAutoDownload\TelegramAutoDownload.exe"
set "INSTALLER_PATH=installer_output\TelegramAutoDownload-Setup-v%APP_VERSION%.exe"

REM [1/8] Python
echo [1/8] Checking Python installation...
python --version
if errorlevel 1 (
    call :fail "Python is not installed or not in PATH. Please install Python 3.8+ and try again."
    goto :end
)

REM [2/8] Clean (build_env is recreated so the bundle always matches requirements.txt)
echo [2/8] Cleaning previous builds...
for %%D in (build dist installer_output build_env) do (
    if exist "%%D" rmdir /s /q "%%D"
    if exist "%%D" (
        call :fail "Could not remove %%D\. A file in it is in use - close any running installer, the app or Explorer window using it and try again."
        goto :end
    )
)
REM Keep our custom telegram_bot.spec file - only delete auto-generated ones
for %%f in (*.spec) do (
    if not "%%f"=="telegram_bot.spec" del "%%f"
)
if exist "version_info.txt" del "version_info.txt"

REM [3/8] Virtual environment
echo [3/8] Setting up build environment...
python -m venv build_env
if errorlevel 1 (
    call :fail "Failed to create virtual environment."
    goto :end
)
call build_env\Scripts\activate.bat
if errorlevel 1 (
    call :fail "Failed to activate virtual environment."
    goto :end
)

REM [4/8] Dependencies
echo [4/8] Installing build dependencies...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
    call :fail "Failed to upgrade pip/setuptools/wheel."
    goto :end
)
python -m pip install -r requirements.txt
if errorlevel 1 (
    call :fail "Failed to install requirements.txt."
    goto :end
)
REM yt-dlp must be latest: X/YouTube change their APIs often and old versions break
python -m pip install --upgrade yt-dlp pyinstaller
if errorlevel 1 (
    call :fail "Failed to install yt-dlp / pyinstaller."
    goto :end
)

REM [5/8] Assets
echo [5/8] Creating application assets...
python create_version_info.py
if errorlevel 1 (
    call :fail "Failed to create version info."
    goto :end
)
python create_icon.py
if errorlevel 1 (
    call :fail "Failed to create application icon."
    goto :end
)

REM [6/8] Syntax check
echo [6/8] Testing application syntax...
python -m py_compile main.py
if errorlevel 1 (
    call :fail "Syntax errors detected in main.py."
    goto :end
)

REM [7/8] Executable
echo [7/8] Building Windows executable...
if not exist "telegram_bot.spec" (
    call :fail "telegram_bot.spec not found."
    goto :end
)
pyinstaller telegram_bot.spec --clean --noconfirm
if errorlevel 1 (
    call :fail "PyInstaller failed."
    goto :end
)
if not exist "%EXE_PATH%" (
    call :fail "Executable build failed: %EXE_PATH% not found."
    goto :end
)
echo Executable built successfully.

REM [8/8] Installer
echo [8/8] Building Windows installer...
set "INNO_SETUP_PATH="
for %%P in (
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    "C:\Program Files\Inno Setup 5\ISCC.exe"
) do (
    if not defined INNO_SETUP_PATH if exist %%P set "INNO_SETUP_PATH=%%~P"
)

if not defined INNO_SETUP_PATH (
    call :fail "Inno Setup not found. Install it from https://jrsoftware.org/isinfo.php and run again."
    goto :end
)

"%INNO_SETUP_PATH%" installer.iss
if errorlevel 1 (
    call :fail "Inno Setup failed."
    goto :end
)
if not exist "%INSTALLER_PATH%" (
    call :fail "Installer creation failed: %INSTALLER_PATH% not found."
    goto :end
)
echo Installer created successfully!

:end
echo.
echo ====================================
if "%ERROR_OCCURRED%"=="0" (
    echo BUILD COMPLETED SUCCESSFULLY!
    echo ====================================
    echo.
    echo Build started at: %START_TIME%
    echo Build ended at:   %TIME%
    echo.
    echo Created files:
    for %%A in ("%EXE_PATH%") do echo - Executable: %%~fA ^(%%~zA bytes^)
    for %%A in ("%INSTALLER_PATH%") do echo - Installer:  %%~fA ^(%%~zA bytes^)
) else (
    echo BUILD FAILED!
    echo ====================================
    echo.
    echo Please check the errors above and try again.
)
echo.
pause
if "%ERROR_OCCURRED%"=="1" exit /b 1
exit /b 0

REM ===== Subroutines =====
:fail
set "ERROR_OCCURRED=1"
echo.
echo ERROR: %~1
exit /b 0
