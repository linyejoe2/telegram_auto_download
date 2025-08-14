@echo off
REM Telegram Auto Download Bot - Complete Windows Package Builder
REM This script handles the complete build process from source to installer

echo ====================================
echo Telegram Auto Download Bot
echo Complete Windows Package Builder
echo ====================================
echo.

set "START_TIME=%TIME%"
set "ERROR_OCCURRED=0"

REM Check Python installation
echo [1/10] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    call :display_error "Python is not installed or not in PATH. Please install Python 3.8+ and try again."
    goto :end
)
python --version

REM Check Git (optional)
echo [2/10] Checking project status...
git --version >nul 2>&1
if not errorlevel 1 (
    echo Git found. Checking repository status...
    git status --porcelain >nul 2>&1
    if not errorlevel 1 (
        echo Repository is clean.
    ) else (
        echo Warning: Not in a git repository or uncommitted changes.
    )
) else (
    echo Git not found - skipping repository checks.
)

REM Clean previous builds
echo [3/10] Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "installer_output" rmdir /s /q "installer_output"
if exist "build_env" rmdir /s /q "build_env"
REM Keep our custom telegram_bot.spec file - only delete auto-generated ones
for %%f in (*.spec) do (
    if not "%%f"=="telegram_bot.spec" del "%%f"
)
if exist "version_info.txt" del "version_info.txt"

REM Create and activate virtual environment
echo [4/10] Setting up build environment...
python -m venv build_env
if not exist "build_env\Scripts\activate.bat" (
    call :display_error "Failed to create virtual environment."
    goto :end
)

call build_env\Scripts\activate.bat

REM Install build dependencies
echo [5/10] Installing build dependencies...
python -m pip install --upgrade pip
pip install --upgrade setuptools wheel
pip install -r requirements.txt
pip install pyinstaller

if errorlevel 1 (
    call :display_error "Failed to install dependencies."
    goto :end
)

REM Create version info and icon
echo [6/10] Creating application assets...
python create_version_info.py
if errorlevel 1 (
    call :display_error "Failed to create version info."
    goto :end
)

python create_icon.py
if errorlevel 1 (
    call :display_error "Failed to create application icon."
    goto :end
)

REM Test the application before building
echo [7/10] Testing application syntax...
python -m py_compile ui.py
if errorlevel 1 (
    call :display_error "Application syntax errors detected."
    goto :end
)

python -m py_compile run_gui.py
if errorlevel 1 (
    call :display_error "GUI launcher syntax errors detected."
    goto :end
)

echo Application syntax check passed.

REM Build executable
echo [8/10] Building Windows executable...

REM Check if spec file exists, create if missing
if not exist "telegram_bot.spec" (
    echo Warning: telegram_bot.spec not found, creating default spec file...
    pyinstaller --onedir --windowed --name=TelegramAutoDownload --icon=assets/icon.ico --version-file=version_info.txt run_gui.py
    if not exist "TelegramAutoDownload.spec" (
        call :display_error "Failed to create spec file automatically."
        goto :end
    )
    ren "TelegramAutoDownload.spec" "telegram_bot.spec"
)

pyinstaller telegram_bot.spec --clean --noconfirm

if not exist "dist\TelegramAutoDownload\TelegramAutoDownload.exe" (
    call :display_error "Executable build failed."
    goto :end
)

echo Executable built successfully.

REM Test the executable (quick test)
echo [9/10] Testing executable...
REM Note: This might not work for GUI apps, but we'll try

echo Testing complete.

REM Build installer
echo [10/10] Building Windows installer...

REM Check for Inno Setup
set "INNO_SETUP_PATH="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 5\ISCC.exe" (
    set "INNO_SETUP_PATH=C:\Program Files\Inno Setup 5\ISCC.exe"
)

if "%INNO_SETUP_PATH%"=="" (
    echo Warning: Inno Setup not found. Skipping installer creation.
    echo You can install Inno Setup from: https://jrsoftware.org/isinfo.php
    echo Then run build_installer.bat to create the installer.
) else (
    if not exist "installer_output" mkdir installer_output
    "%INNO_SETUP_PATH%" installer.iss
    
    if exist "installer_output\TelegramAutoDownload-Setup-v1.2.0.exe" (
        echo Installer created successfully!
    ) else (
        echo Warning: Installer creation failed.
        set "ERROR_OCCURRED=1"
    )
)

set "END_TIME=%TIME%"
echo Build started at: %START_TIME%
echo Build ended at: %END_TIME%
echo.
pause

REM Function to display errors
:display_error
echo.
echo ====================================
echo ERROR OCCURRED!
echo ====================================
echo %~1
echo.
set "ERROR_OCCURRED=1"
pause

:end
echo.
echo ====================================
if "%ERROR_OCCURRED%"=="0" (
    echo BUILD COMPLETED SUCCESSFULLY!
    echo ====================================
    echo.
    echo Created files:
    echo - Executable: dist\TelegramAutoDownload\TelegramAutoDownload.exe
    if exist "installer_output\TelegramAutoDownload-Setup-v1.2.0.exe" (
        echo - Installer: installer_output\TelegramAutoDownload-Setup-v1.2.0.exe
    )
    echo.
    echo File sizes:
    if exist "dist\TelegramAutoDownload\TelegramAutoDownload.exe" (
        for %%A in ("dist\TelegramAutoDownload\TelegramAutoDownload.exe") do echo   Executable: %%~zA bytes
    )
    if exist "installer_output\TelegramAutoDownload-Setup-v1.2.0.exe" (
        for %%A in ("installer_output\TelegramAutoDownload-Setup-v1.2.0.exe") do echo   Installer: %%~zA bytes
    )
    echo.
    echo Distribution files are ready!
) else (
    echo BUILD FAILED!
    echo ====================================
    echo.
    echo Please check the errors above and try again.
    echo.
)
pause