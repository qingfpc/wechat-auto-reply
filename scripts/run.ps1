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
& $python -m wechat_draft_brain
