[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
AppId={{A5B3C2D1-E4F6-4A7B-8C9D-1E2F3A4B5C6D}}
AppName=Telegram Auto Download Bot
AppVersion=1.3.0
AppVerName=Telegram Auto Download Bot v1.3.0
AppPublisher=Telegram Auto Download Bot
AppPublisherURL=https://github.com/your-repo/telegram_auto_download
AppSupportURL=https://github.com/your-repo/telegram_auto_download/issues
AppUpdatesURL=https://github.com/your-repo/telegram_auto_download/releases
DefaultDirName={autopf}\TelegramAutoDownload
DisableProgramGroupPage=yes
; Remove the following line to run in administrative install mode (install for all users)
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=TelegramAutoDownload-Setup-v1.3.0
SetupIconFile=assets\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\TelegramAutoDownload.exe
UninstallDisplayName=Telegram Auto Download Bot

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode
Name: "startmenu"; Description: "Create Start Menu entry"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\TelegramAutoDownload\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "fix_windows_security.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
; NOTE: Don't use "Flags: ignoreversion" on any shared system files

[Icons]
Name: "{autoprograms}\Telegram Auto Download Bot"; Filename: "{app}\TelegramAutoDownload.exe"; Tasks: startmenu
Name: "{autodesktop}\Telegram Auto Download Bot"; Filename: "{app}\TelegramAutoDownload.exe"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\Telegram Auto Download Bot"; Filename: "{app}\TelegramAutoDownload.exe"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\TelegramAutoDownload.exe"; Description: "{cm:LaunchProgram,Telegram Auto Download Bot}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\fix_windows_security.bat"; Description: "Fix Windows Security false positives (run as administrator)"; Flags: runasoriginaluser postinstall unchecked

[UninstallDelete]
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.session"
Type: files; Name: "{app}\*.db"
Type: dirifempty; Name: "{app}\logs"
Type: dirifempty; Name: "{app}"

[Code]
function GetUninstallString(): String;
var
  sUnInstPath: String;
  sUnInstallString: String;
begin
  sUnInstPath := ExpandConstant('Software\Microsoft\Windows\CurrentVersion\Uninstall\{#emit SetupSetting("AppId")}_is1');
  sUnInstallString := '';
  if not RegQueryStringValue(HKLM, sUnInstPath, 'UninstallString', sUnInstallString) then
    RegQueryStringValue(HKCU, sUnInstPath, 'UninstallString', sUnInstallString);
  Result := sUnInstallString;
end;

function IsUpgrade(): Boolean;
begin
  Result := (GetUninstallString() <> '');
end;

function UnInstallOldVersion(): Integer;
var
  sUnInstallString: String;
  iResultCode: Integer;
begin
  Result := 0;
  sUnInstallString := GetUninstallString();
  if sUnInstallString <> '' then begin
    sUnInstallString := RemoveQuotes(sUnInstallString);
    if Exec(sUnInstallString, '/SILENT /NORESTART /SUPPRESSMSGBOXES','', SW_HIDE, ewWaitUntilTerminated, iResultCode) then
      Result := 3
    else
      Result := 2;
  end else
    Result := 1;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep=ssInstall) then
  begin
    if (IsUpgrade()) then
    begin
      UnInstallOldVersion();
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // Check if application is already running
  if CheckForMutexes('TelegramAutoDownloadBotMutex') then
  begin
    if MsgBox('Telegram Auto Download Bot is currently running. Please close it before continuing with the installation.', mbError, MB_OKCANCEL) = IDCANCEL then
      Result := False;
  end;
end;