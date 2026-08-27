$ErrorActionPreference = "Stop"
$envPath = "D:\Anaconda_envs\envs\wechat-draft-brain\python.exe"
if (-not (Test-Path $envPath)) {
  Write-Error "找不到 conda 环境: $envPath"
}
Set-Location $PSScriptRoot\..
& $envPath -m wechat_draft_brain.app
