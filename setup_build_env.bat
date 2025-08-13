@echo off
REM Setup Build Environment for Telegram Auto Download Bot
REM This script installs all necessary tools for building Windows installer

echo ====================================
echo Build Environment Setup
echo ====================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running as administrator - good!
) else (
    echo Warning: Not running as administrator. Some installations may fail.
    echo Recommend running this script as administrator.
    echo.
)

REM Check if Chocolatey is installed
choco version >nul 2>&1
if errorlevel 1 (
    echo [1/4] Installing Chocolatey package manager...
    echo This will install Chocolatey to help manage dependencies.
    echo.
    powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
    
    if errorlevel 1 (
        echo Failed to install Chocolatey. Please install manually.
        goto :manual_install
    )
    
    REM Refresh environment variables
    call refreshenv
) else (
    echo [1/4] Chocolatey already installed
    choco version
)

REM Install Python if not present
echo [2/4] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo Installing Python...
    choco install python -y
    call refreshenv
) else (
    echo Python already installed:
    python --version
)

REM Install Git if not present
echo [3/4] Checking Git installation...
git --version >nul 2>&1
if errorlevel 1 (
    echo Installing Git...
    choco install git -y
    call refreshenv
) else (
    echo Git already installed:
    git --version
)

REM Install Inno Setup if not present
echo [4/4] Checking Inno Setup installation...
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    echo Inno Setup 6 already installed
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    echo Inno Setup 6 already installed
) else if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (
    echo Inno Setup 5 already installed
) else if exist "C:\Program Files\Inno Setup 5\ISCC.exe" (
    echo Inno Setup 5 already installed
) else (
    echo Installing Inno Setup...
    choco install innosetup -y
    call refreshenv
)

goto :success

:manual_install
echo.
echo ====================================
echo MANUAL INSTALLATION REQUIRED
echo ====================================
echo.
echo Please install the following manually:
echo.
echo 1. Python 3.8+: https://python.org/downloads/
echo 2. Git: https://git-scm.com/download/win
echo 3. Inno Setup: https://jrsoftware.org/isinfo.php
echo.
echo After installation, run package_windows.bat to build the installer.
echo.
goto :end

:success
echo.
echo ====================================
echo SETUP COMPLETE!
echo ====================================
echo.
echo All build dependencies are now installed:
echo.
python --version 2>nul && echo ✅ Python installed || echo ❌ Python missing
git --version 2>nul && echo ✅ Git installed || echo ❌ Git missing
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (echo ✅ Inno Setup 6 installed) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (echo ✅ Inno Setup 6 installed) else if exist "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" (echo ✅ Inno Setup 5 installed) else if exist "C:\Program Files\Inno Setup 5\ISCC.exe" (echo ✅ Inno Setup 5 installed) else (echo ❌ Inno Setup missing)
echo.
echo You can now run: package_windows.bat
echo.

:end
pause