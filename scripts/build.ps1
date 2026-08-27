$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "D:\Anaconda_envs\envs\wechat-draft-brain\python.exe"
if (-not (Test-Path $python)) {
  $cmd = Get-Command python -ErrorAction SilentlyContinue
  if (-not $cmd) {
    Write-Error "找不到 Python。请先 conda activate wechat-draft-brain"
  }
  $python = $cmd.Source
}

Set-Location $root
Write-Host "使用 Python: $python"

& $python -m pip install -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python packaging\make_icon.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m PyInstaller packaging\night_desk.spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$exe = Join-Path $root "dist\NightDesk\NightDesk.exe"
if (-not (Test-Path $exe)) {
  Write-Error "未生成 $exe"
}

$isccCandidates = @(
  "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
  "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)
$iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
  Write-Host "未找到 Inno Setup，尝试用 winget 安装…"
  winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
  $iscc = $isccCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $iscc) {
  Write-Error "仍未找到 ISCC.exe。请安装 Inno Setup 6 后重新运行 scripts/build.ps1"
}

& $iscc (Join-Path $root "packaging\night_desk.iss")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$setup = Join-Path $root "dist\夜班台-Setup.exe"
Write-Host "目录版: $exe"
if (Test-Path $setup) {
  Write-Host "安装包: $setup"
} else {
  Get-ChildItem (Join-Path $root "dist") -Filter "*Setup*.exe" | ForEach-Object { Write-Host "安装包: $($_.FullName)" }
}
