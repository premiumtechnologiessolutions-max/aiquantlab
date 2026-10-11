$ErrorActionPreference = "Stop"
$TaskName = "AI Quant Lab Always On"

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed '$TaskName'." -ForegroundColor Green
} else {
    Write-Host "'$TaskName' is not installed."
}
