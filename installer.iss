#define AppVersion "2.1.0"
[Setup]
AppId={{E733661E-35C8-45F3-93A7-CA839B1AA342}
AppName=ClipMerge
AppVersion={#AppVersion}
AppPublisher=ClipMerge
AppVerName=ClipMerge {#AppVersion}
DefaultDirName={localappdata}\Programs\ClipMerge
DefaultGroupName=ClipMerge
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..
OutputBaseFilename=ClipMerge-Setup-{#AppVersion}
SetupIconFile=ClipMerge.ico
UninstallDisplayIcon={app}\ClipMerge.exe
WizardStyle=modern
WizardSizePercent=110
WizardImageFile=wizard.bmp
WizardSmallImageFile=wizard-small.bmp
DisableProgramGroupPage=yes
DisableWelcomePage=no
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName=ClipMerge
VersionInfoDescription=ClipMerge Setup
#ifdef TestBuild
CreateUninstallRegKey=no
#endif

[Languages]
Name: "vietnamese"; MessagesFile: "compiler:Default.isl"

[Messages]
vietnamese.WizardSelectDir=Thư mục cài đặt
vietnamese.WizardSelectTasks=Tùy chọn
vietnamese.WizardReady=Sẵn sàng cài đặt
vietnamese.WizardPreparing=Chuẩn bị cài đặt
vietnamese.WizardInstalling=Đang cài đặt
vietnamese.WizardUninstalling=Đang gỡ cài đặt
vietnamese.StatusExtractFiles=Đang giải nén...
vietnamese.StatusCreateDirs=Đang tạo thư mục...
vietnamese.StatusCreateIcons=Đang tạo lối tắt...
vietnamese.StatusCreateRegistryEntries=Đang đăng ký ứng dụng...
vietnamese.StatusSavingUninstall=Đang lưu thông tin gỡ cài đặt...
vietnamese.StatusRunProgram=Đang hoàn tất...
vietnamese.StatusUninstalling=Đang gỡ %1...
vietnamese.UninstallStatusLabel=Vui lòng chờ trong khi gỡ %1.
vietnamese.ExitSetupTitle=Thoát cài đặt
vietnamese.ExitSetupMessage=Quá trình cài đặt chưa hoàn tất.%n%nBạn muốn thoát?
vietnamese.ButtonYes=&Có
vietnamese.ButtonNo=&Không
vietnamese.ButtonWizardBrowse=&Duyệt...
vietnamese.DiskSpaceGBLabel=Cần tối thiểu [gb] GB trống.
vietnamese.DiskSpaceMBLabel=Cần tối thiểu [mb] MB trống.
vietnamese.BeveledLabel=ClipMerge
vietnamese.ButtonBack=< &Quay lại
vietnamese.ButtonNext=&Tiếp tục >
vietnamese.ButtonInstall=&Cài đặt
vietnamese.ButtonCancel=&Hủy
vietnamese.ButtonFinish=&Hoàn tất
vietnamese.SetupAppTitle=Cài đặt ClipMerge
vietnamese.SetupWindowTitle=Cài đặt ClipMerge
vietnamese.WelcomeLabel1=Cài đặt ClipMerge
vietnamese.WelcomeLabel2=Ghép video, tạo tác vụ và thay âm thanh.%n%nNhấn Tiếp tục để bắt đầu.
vietnamese.SelectDirLabel3=Chọn thư mục cài đặt ClipMerge.
vietnamese.SelectDirBrowseLabel=Nhấn Tiếp tục để dùng thư mục này hoặc Duyệt để chọn vị trí khác.
vietnamese.SelectDirDesc=Bạn muốn cài ClipMerge vào đâu?
vietnamese.ButtonBrowse=&Duyệt...
vietnamese.SelectTasksLabel2=Chọn các tùy chọn bổ sung.
vietnamese.SelectTasksDesc=Tùy chọn
vietnamese.ReadyLabel1=Sẵn sàng cài đặt ClipMerge.
vietnamese.ReadyLabel2a=Nhấn Cài đặt để tiếp tục.
vietnamese.ReadyLabel2b=Nhấn Cài đặt để tiếp tục.
vietnamese.ReadyMemoDir=Thư mục cài đặt:
vietnamese.ReadyMemoTasks=Tùy chọn:
vietnamese.InstallingLabel=Đang cài đặt ClipMerge. Vui lòng chờ.
vietnamese.FinishedHeadingLabel=Đã cài đặt ClipMerge
vietnamese.FinishedLabelNoIcons=ClipMerge đã sẵn sàng sử dụng.
vietnamese.FinishedLabel=ClipMerge đã sẵn sàng sử dụng. Nhấn Hoàn tất để đóng bộ cài.
vietnamese.ConfirmUninstall=Gỡ %1 và các thành phần đã cài đặt?
vietnamese.UninstalledAll=Đã gỡ cài đặt %1.
vietnamese.UninstallAppFullTitle=Gỡ cài đặt %1
vietnamese.UninstallAppTitle=Gỡ ClipMerge

[Tasks]
Name: "desktopicon"; Description: "Tạo lối tắt ngoài Desktop"; Flags: unchecked

[Files]
Source: "ClipMerge.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ClipMerge.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "ClipMerge.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "bin\*"; DestDir: "{app}\bin"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

#ifndef TestBuild
[Icons]
Name: "{group}\ClipMerge"; Filename: "{app}\ClipMerge.exe"; WorkingDir: "{app}"; AppUserModelID: "ClipMerge.Desktop"
Name: "{autodesktop}\ClipMerge"; Filename: "{app}\ClipMerge.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "ClipMerge.Desktop"
#endif

[Run]
Filename: "{app}\ClipMerge.exe"; Description: "Mở ClipMerge"; Flags: nowait postinstall skipifsilent
Filename: "{app}\ClipMerge.exe"; Flags: nowait skipifnotsilent
