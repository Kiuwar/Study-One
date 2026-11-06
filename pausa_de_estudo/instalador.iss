; Instalador do Pausa de Estudo (Inno Setup 6). Instala só para o usuário atual,
; em %LOCALAPPDATA%\Programs, pasta onde o app consegue gravar config.json e historico.db.
#define AppName "Pausa de Estudo"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B6B0D3C2-5C0B-4C3E-9A55-6E7A3D1F2A10}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\PausaDeEstudo
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=PausaDeEstudo-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=icone.ico
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\PausaDeEstudo.exe

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked

[Files]
Source: "dist\PausaDeEstudo\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Pausa de Estudo"; Filename: "{app}\PausaDeEstudo.exe"
Name: "{group}\Resumo das pausas"; Filename: "{app}\PausaDeEstudo.exe"; Parameters: "--estatisticas"
Name: "{group}\Encerrar Pausa de Estudo"; Filename: "{app}\PausaDeEstudo.exe"; Parameters: "--sair"
Name: "{userdesktop}\Pausa de Estudo"; Filename: "{app}\PausaDeEstudo.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PausaDeEstudo.exe"; Description: "Abrir o Pausa de Estudo agora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\PausaDeEstudo.exe"; Parameters: "--sair"; Flags: runhidden; RunOnceId: "EncerrarApp"

[UninstallDelete]
; atalho de início automático criado pelo próprio app (opção iniciar_com_windows)
Type: files; Name: "{userappdata}\Microsoft\Windows\Start Menu\Programs\Startup\Pausa de Estudo.lnk"

[Code]
// Em atualização, encerra a versão em execução para os arquivos poderem ser trocados.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Codigo: Integer;
begin
  if FileExists(ExpandConstant('{app}\PausaDeEstudo.exe')) then
    Exec(ExpandConstant('{app}\PausaDeEstudo.exe'), '--sair', '', SW_HIDE, ewWaitUntilTerminated, Codigo);
  Result := '';
end;
