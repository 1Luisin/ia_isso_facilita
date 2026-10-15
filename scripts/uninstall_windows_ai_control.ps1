$ErrorActionPreference = "Stop"
$Shell = New-Object -ComObject WScript.Shell
$Desktop = $Shell.SpecialFolders.Item("Desktop")
$StartMenuDirectory = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Isso Facilita"
$ShortcutPaths = @(
    (Join-Path $Desktop "Isso Facilita - Controle da IA.lnk"),
    (Join-Path $StartMenuDirectory "Controle da IA.lnk")
)

foreach ($ShortcutPath in $ShortcutPaths) {
    if (Test-Path -LiteralPath $ShortcutPath -PathType Leaf) {
        Remove-Item -LiteralPath $ShortcutPath -Force
    }
}

if ((Test-Path -LiteralPath $StartMenuDirectory -PathType Container) -and
    -not (Get-ChildItem -LiteralPath $StartMenuDirectory -Force)) {
    Remove-Item -LiteralPath $StartMenuDirectory -Force
}

Write-Output "Atalhos do controle da IA removidos."
