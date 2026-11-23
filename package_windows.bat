@echo off
REM Telegram Auto Download Bot - Complete Windows Package Builder
REM Builds the executable with PyInstaller, then the installer with Inno Setup.
REM Any failing step stops the build immediately.
REM Fast by default: build_env\ and the PyInstaller cache in build\ are reused between builds.
REM   package_windows.bat fresh   = rebuild everything from scratch (new build_env, no cache)

setlocal

echo ====================================
echo Telegram Auto Download Bot
echo Complete Windows Package Builder
echo ====================================
echo.

set "START_TIME=%TIME%"
set "ERROR_OCCURRED=0"
set "FRESH=0"
if /i "%~1"=="fresh" set "FRESH=1"

REM ===== Version constant =====
set "APP_VERSION=3.3.1"
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

REM [2/8] Clean: only the outputs, unless "fresh" (then also the cache and build_env)
echo [2/8] Cleaning previous builds...
set "CLEAN_DIRS=dist installer_output"
if "%FRESH%"=="1" (
    echo Fresh build: removing build_env\ and the PyInstaller cache too
    set "CLEAN_DIRS=build dist installer_output build_env"
)
REM A folder that is someone's current directory (open terminal / Explorer) can't be removed itself,
REM but an empty leftover is harmless: only fail when files inside are still in use.
for %%D in (%CLEAN_DIRS%) do (
    if exist "%%D" rmdir /s /q "%%D" 2>nul
    if exist "%%D" (
        dir /b /a "%%D" 2>nul | findstr . >nul
        if not errorlevel 1 (
            call :fail "Could not remove files in %%D\. A file in it is in use - close any running installer, the app or Explorer window using it and try again."
            goto :end
        )
        echo Note: %%D\ is open in another window, kept the empty folder.
    )
)
REM Keep our custom telegram_bot.spec file - only delete auto-generated ones
for %%f in (*.spec) do (
    if not "%%f"=="telegram_bot.spec" del "%%f"
)
if exist "version_info.txt" del "version_info.txt"

REM [3/8] Virtual environment
echo [3/8] Setting up build environment...
set "NEW_ENV=0"
if not exist "build_env\Scripts\python.exe" (
    set "NEW_ENV=1"
    python -m venv build_env
    if errorlevel 1 (
        call :fail "Failed to create virtual environment."
        goto :end
    )
) else (
    echo Reusing build_env\ ^(run "package_windows.bat fresh" to recreate it^)
)
call build_env\Scripts\activate.bat
if errorlevel 1 (
    call :fail "Failed to activate virtual environment."
    goto :end
)

REM [4/8] Dependencies
echo [4/8] Installing build dependencies...
if "%NEW_ENV%"=="1" (
    python -m pip install --upgrade pip setuptools wheel
    if errorlevel 1 (
        call :fail "Failed to upgrade pip/setuptools/wheel."
        goto :end
    )
)
REM quick when everything is already installed; only new / changed requirements are downloaded
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
REM Web library frontend (React + Tailwind) is built into library\static and bundled by PyInstaller
where npm >nul 2>nul
if errorlevel 1 (
    call :fail "Node.js / npm not found. Install Node.js 18+ (https://nodejs.org) to build the web library frontend."
    goto :end
)
pushd frontend
call npm ci
if errorlevel 1 (
    popd
    call :fail "npm ci failed in frontend\."
    goto :end
)
call npm run build
if errorlevel 1 (
    popd
    call :fail "Web frontend build failed (npm run build)."
    goto :end
)
popd
if not exist "library\static\index.html" (
    call :fail "Web frontend build output library\static\index.html not found."
    goto :end
)
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
if "%FRESH%"=="1" (
    pyinstaller telegram_bot.spec --clean --noconfirm
) else (
    pyinstaller telegram_bot.spec --noconfirm
)
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
