# Windows Build Guide

Complete guide for building Windows installer package.

## Quick Build

```batch
package_windows.bat    # Complete build process
build_windows.bat      # Executable only
build_installer.bat    # Installer only
```

## Prerequisites

- **Python 3.8+**: <https://python.org/downloads/>
- **Inno Setup 6.x**: <https://jrsoftware.org/isinfo.php>
- **Git** (optional): <https://git-scm.com/download/win>

## Build Output

**Successful build creates:**

- `dist/TelegramAutoDownload/TelegramAutoDownload.exe` (~150-300 MB)
- `installer_output/TelegramAutoDownload-Setup-v0.5.1.exe` (~100-200 MB)

## Configuration Files

| File | Purpose |
|------|---------|
| `telegram_bot.spec` | PyInstaller configuration |
| `installer.iss` | Inno Setup installer configuration |
| `create_version_info.py` | Version information generator |
| `create_icon.py` | Application icon generator |

## Troubleshooting

| Error | Solution |
|-------|----------|
| "Python not found" | Install Python and add to PATH |
| "Inno Setup not found" | Install from official website |
| "PyInstaller failed" | Check syntax: `python -m py_compile ui.py` |
| "Import errors in .exe" | Add modules to `hiddenimports` in `.spec` file |

## Installer Features

- Professional Windows installer
- Start menu and desktop shortcuts (optional)
- Auto-upgrade handling
- Clean uninstall with log cleanup
- No admin privileges required

## Version Management

Update version numbers in:

1. `create_version_info.py`
2. `installer.iss`
3. `package_windows.bat`

## Distribution

**Installer**: Works on any Windows 10/11 system without dependencies
**Portable**: Zip the `dist/TelegramAutoDownload/` folder for portable use

**Silent Install Options:**

- `setup.exe /SILENT`
- `setup.exe /VERYSILENT /NORESTART`
- `setup.exe /DIR="C:\CustomPath"`
