$ErrorActionPreference = 'Stop'
$exe = Join-Path $PSScriptRoot 'Aegis.exe'
if (-not (Test-Path -LiteralPath $exe)) { $exe = Join-Path $PSScriptRoot 'dist\Aegis\Aegis.exe' }
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build or extract Aegis before installing shortcuts.' }
$exe = (Resolve-Path -LiteralPath $exe).Path
$shellObject = New-Object -ComObject WScript.Shell
$destinations = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))
foreach ($folder in $destinations) {
    $shortcut = $shellObject.CreateShortcut((Join-Path $folder 'Aegis File Organizer.lnk'))
    $shortcut.TargetPath = $exe
    $shortcut.WorkingDirectory = Split-Path -Parent $exe
    $shortcut.Description = 'Preview, organize, and undo file organization with Aegis'
    $shortcut.Save()
}
Write-Host 'Aegis shortcuts installed on your Desktop and Start menu.'
