#define MyAppName "夜班台"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "qingfpc"
#define MyAppExeName "NightDesk.exe"

[Setup]
AppId={{A7C3E1B2-4F8D-4A91-9C2E-1B6D8F0A3E7C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/qingfpc/wechat-auto-reply
DefaultDirName={localappdata}\Programs\NightDesk
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=夜班台-Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible
; 卸载不删除 %APPDATA%\夜班台 里的草稿库和用户配置。

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"
Name: "startup"; Description: "开机时启动"; GroupDescription: "附加选项:"; Flags: unchecked

[Files]
Source: "..\dist\NightDesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startup

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即运行夜班台"; Flags: nowait postinstall skipifsilent
