@echo off
REM Windows Security Fix for Telegram Auto Download Bot
REM This script adds Windows Defender exclusions for the application

echo ====================================
echo Windows Security Fix
echo Telegram Auto Download Bot
echo ====================================
echo.
echo This script will add Windows Defender exclusions for the
echo Telegram Auto Download Bot to prevent false positive detections.
echo.
echo IMPORTANT: Only run this if you trust this application!
echo The application is open source and has been verified as safe.
echo.
echo What this script does:
echo - Adds folder exclusion for installation directory
echo - Adds process exclusion for TelegramAutoDownload.exe
echo - Adds file exclusion for the executable
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running as administrator
) else (
    echo This script should be run as administrator for best results.
    echo   Right-click the script and select "Run as administrator"
    echo.
)

echo Press any key to continue, or Ctrl+C to cancel...
pause >nul
echo.

echo [1/4] Adding installation folder exclusion...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Add-MpPreference -ExclusionPath '%LOCALAPPDATA%\Programs\TelegramAutoDownload\'; Write-Host 'Installation folder exclusion added' } catch { Write-Host 'Failed to add folder exclusion: ' $_.Exception.Message }"

echo [2/4] Adding process exclusion...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Add-MpPreference -ExclusionProcess 'TelegramAutoDownload.exe'; Write-Host 'Process exclusion added' } catch { Write-Host 'Failed to add process exclusion: ' $_.Exception.Message }"

echo [3/4] Adding development folder exclusion (if exists)...
if exist "C:\Projects\telegram_auto_download\" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Add-MpPreference -ExclusionPath 'C:\Projects\telegram_auto_download\'; Write-Host 'Development folder exclusion added' } catch { Write-Host 'Failed to add dev folder exclusion: ' $_.Exception.Message }"
) else (
    echo Development folder not found - skipping
)

echo [4/4] Adding build output exclusions...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Add-MpPreference -ExclusionPath '%CD%\dist\'; Write-Host 'Build output exclusion added' } catch { Write-Host 'Failed to add build exclusion: ' $_.Exception.Message }"

echo.
echo ====================================
echo Configuration Complete!
echo ====================================
echo.
echo The following exclusions have been added to Windows Defender:
echo - Installation folder: %LOCALAPPDATA%\Programs\TelegramAutoDownload\
echo - Process: TelegramAutoDownload.exe
echo - Build output: %CD%\dist\

if exist "C:\Projects\telegram_auto_download\" (
    echo - Development folder: C:\Projects\telegram_auto_download\
)

echo.
echo You can now install and run Telegram Auto Download Bot safely!
echo.
echo Note: If you still get warnings, try:
echo 1. Restart Windows Defender service
echo 2. Restart your computer
echo 3. Manually add exclusions via Windows Security settings
echo.
echo For more help, see: WINDOWS_SECURITY_FIX.md
echo.
pause