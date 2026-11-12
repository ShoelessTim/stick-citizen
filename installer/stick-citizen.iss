; Stick Citizen installer (Inno Setup). Built in CI: ISCC /DAppVersion=3.5.1 /DSourceExe=dist\StickCitizen-v3.5.1.exe
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceExe
  #define SourceExe "..\dist\StickCitizen.exe"
#endif

[Setup]
AppId={{6E0C2C6B-5B0B-4C1E-9A54-5C17C1717E51}
AppName=Stick Citizen
AppVersion={#AppVersion}
AppPublisher=ShoelessTim
AppPublisherURL=https://github.com/ShoelessTim/stick-citizen
DefaultDirName={localappdata}\Programs\Stick Citizen
DefaultGroupName=Stick Citizen
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=StickCitizen-v{#AppVersion}-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\StickCitizen.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Put an icon on the desktop"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "StickCitizen.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Stick Citizen"; Filename: "{app}\StickCitizen.exe"
Name: "{autodesktop}\Stick Citizen"; Filename: "{app}\StickCitizen.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\StickCitizen.exe"; Description: "Open Stick Citizen"; Flags: nowait postinstall skipifsilent
