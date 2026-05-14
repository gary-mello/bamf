$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --clean --noconfirm bamf-web.spec
python -m PyInstaller --clean --noconfirm bamf-cli.spec

Write-Host ""
Write-Host "Built dist\bamf-web.exe and dist\bamf-cli.exe"
Write-Host "Web:  .\dist\bamf-web.exe"
Write-Host "CLI:  .\dist\bamf-cli.exe"
