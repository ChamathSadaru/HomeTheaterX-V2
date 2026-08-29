; HomeTheaterX Professional All-In-One Inno Setup Script
#define MyAppName "HomeTheaterX"
#define MyAppVersion "2.0"
#define MyAppPublisher "Chamathz"
#define MyAppURL "https://github.com/ChamathSadaru/HomeTheaterX-V2"
#define MyAppExeName "HomeTheaterX.exe"

[Setup]
AppId={{C8271A3F-7E59-4D1E-9C64-98F17A02C1E4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=HomeTheaterX_AllInOne_Setup_v2.0
SetupIconFile=Icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "autostart"; Description: "Launch HomeTheaterX automatically when Windows starts (System Tray)"; GroupDescription: "Startup Options:"; Flags: unchecked
Name: "installapo"; Description: "Install Equalizer APO 1.4 (Required for 5.1 DSP & Soundstage Calibration)"; GroupDescription: "Audio Engine Dependencies:"; Check: Not IsAPOInstalled; Flags: checkedonce

[Files]
; Main Executable and Core Resources
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "Icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "Splash.jpg"; DestDir: "{app}"; Flags: ignoreversion
Source: "apo\*"; DestDir: "{app}\apo"; Flags: ignoreversion recursesubdirs createallsubdirs

; Equalizer APO Preset Templates Deployment
Source: "apo\*"; DestDir: "C:\Program Files\EqualizerAPO\config"; Flags: uninsneveruninstall recursesubdirs createallsubdirs; Check: DirExists('C:\Program Files\EqualizerAPO')

; Bundled Equalizer APO 64-bit Installer
Source: "installers\EqualizerAPO64-1.4.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: Not IsAPOInstalled

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\Icon.ico"; Tasks: desktopicon

[Registry]
; Windows Startup Auto-Launch
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "HomeTheaterX"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
; Run Equalizer APO installer if selected and not installed
Filename: "{tmp}\EqualizerAPO64-1.4.exe"; Parameters: "/S"; Tasks: installapo; Flags: waituntilterminated; StatusMsg: "Installing Equalizer APO 1.4 Audio Engine..."; Check: Not IsAPOInstalled
; Launch HomeTheaterX after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function IsAPOInstalled(): Boolean;
begin
  Result := FileExists('C:\Program Files\EqualizerAPO\EqualizerAPO.exe') or
            FileExists('C:\Program Files\EqualizerAPO\Configurator.exe') or
            RegKeyExists(HKLM, 'SOFTWARE\EqualizerAPO');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath: String;
  ConfigContent: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Ensure production APO config directory exists and deploy base config.txt if missing
    if DirExists('C:\Program Files\EqualizerAPO\config') then
    begin
      ConfigPath := 'C:\Program Files\EqualizerAPO\config\config.txt';
      if not FileExists(ConfigPath) then
      begin
        ConfigContent := 'Include: upmixer.txt' + #13#10 +
                         'Include: BassManagement..txt' + #13#10 +
                         '# Include: BassBoostedPreset.txt' + #13#10 +
                         '# Include: TightBassPreset.txt' + #13#10 +
                         '# Include: HallVibePreset.txt' + #13#10 +
                         '# Include: EchoPreset.txt' + #13#10 +
                         '# Include: 8D.txt' + #13#10 +
                         '# Include: RoomCalibration.txt' + #13#10 +
                         '# Include: UpmixForRoomCalibration.txt' + #13#10 +
                         '# Include: RoomShaker.txt' + #13#10;
        SaveStringToFile(ConfigPath, ConfigContent, False);
      end;
    end;
  end;
end;
