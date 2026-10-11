$ErrorActionPreference = "Stop"

$TaskName = "AI Quant Lab Always On"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $PSScriptRoot "run_always_on.ps1"

if (-not (Test-Path $Runner)) {
    throw "Always-on runner not found: $Runner"
}

$PowerShell = (Get-Command powershell.exe).Source
$Action = New-ScheduledTaskAction `
    -Execute $PowerShell `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Runs AI Quant Lab in the signed-in MT5 desktop session and restarts it after failure." `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "Installed and started '$TaskName'." -ForegroundColor Green
Write-Host "Health: http://127.0.0.1:8765/api/health"
Write-Host "Log: $ProjectRoot\data\operational\logs\always-on.log"
