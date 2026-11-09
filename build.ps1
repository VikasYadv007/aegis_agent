$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python virtual environment creation failed.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { throw 'Safety checks failed.' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm Aegis.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
Copy-Item -LiteralPath Install-Shortcuts.ps1, Install-Shortcuts.cmd, README.md, LOGIC_REVIEW.md -Destination dist\Aegis
$outputPath = Join-Path $PSScriptRoot 'build\smoke-result.json'
$env:AEGIS_DATA_DIR = Join-Path $PSScriptRoot 'build\test-settings'
Remove-Item -LiteralPath $outputPath -ErrorAction SilentlyContinue
$process = Start-Process -FilePath "$PSScriptRoot\dist\Aegis\Aegis.exe" -ArgumentList @('--smoke-test', ('"' + $outputPath + '"')) -WindowStyle Hidden -Wait -PassThru
if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $outputPath)) { throw 'Packaged smoke test failed.' }
Compress-Archive -Path dist\Aegis -DestinationPath dist\Aegis-Windows-x64.zip -Force
Get-FileHash -LiteralPath dist\Aegis-Windows-x64.zip -Algorithm SHA256 | Format-List
