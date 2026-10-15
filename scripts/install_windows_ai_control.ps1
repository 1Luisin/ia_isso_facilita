param(
    [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot ".."))
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$Pythonw = Join-Path $ProjectRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path -LiteralPath $Pythonw -PathType Leaf)) {
    throw "Python do projeto não encontrado em $Pythonw. Crie a .venv antes de instalar o controle."
}

$Shell = New-Object -ComObject WScript.Shell
$Desktop = $Shell.SpecialFolders.Item("Desktop")
$StartMenuDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Isso Facilita"
New-Item -ItemType Directory -Path $StartMenuDirectory -Force | Out-Null

$ShortcutPaths = @(
    (Join-Path $Desktop "Isso Facilita - Controle da IA.lnk"),
    (Join-Path $StartMenuDirectory "Controle da IA.lnk")
)

foreach ($ShortcutPath in $ShortcutPaths) {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Pythonw
    $Shortcut.Arguments = "-m isso_facilita.desktop_control"
    $Shortcut.WorkingDirectory = $ProjectRoot
    $Shortcut.IconLocation = "$Pythonw,0"
    $Shortcut.Description = "Ativar ou desativar a IA do Isso Facilita"
    $Shortcut.Save()
}

Write-Output "Controle da IA instalado no Desktop e no Menu Iniciar."
