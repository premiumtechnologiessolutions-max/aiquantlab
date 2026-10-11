param(
    [string]$Pairs = "EURUSD,GBPUSD,USDJPY,USDCHF,AUDUSD,NZDUSD,USDCAD",
    [ValidateSet("M1", "M5", "M15", "H1", "H4", "D1")]
    [string]$Timeframe = "M15",
    [ValidateRange(5, 3600)]
    [int]$MonitorIntervalSeconds = 30
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonPath = Join-Path $ProjectRoot ".venv312\Scripts\python.exe"
$LogRoot = Join-Path $ProjectRoot "data\operational\logs"
$LogPath = Join-Path $LogRoot "always-on.log"

if (-not (Test-Path $PythonPath)) {
    throw "Missing .venv312. Run scripts\start_voice_dashboard.ps1 once before installing always-on mode."
}

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$env:AI_QUANT_ENABLE_DEMO_ORDERS = "false"
Set-Location $ProjectRoot

while ($true) {
    $StartedAt = Get-Date -Format o
    "[$StartedAt] Starting AI Quant Lab always-on process for $Pairs $Timeframe." |
        Out-File -Append -Encoding utf8 $LogPath

    & $PythonPath -X utf8 -m ai_quant_lab voice-dashboard `
        --pairs $Pairs `
        --timeframe $Timeframe `
        --monitor-interval $MonitorIntervalSeconds `
        --auto-monitor `
        --no-open-browser *>> $LogPath

    $ExitCode = $LASTEXITCODE
    $StoppedAt = Get-Date -Format o
    "[$StoppedAt] Process exited with code $ExitCode; restarting in 60 seconds." |
        Out-File -Append -Encoding utf8 $LogPath
    Start-Sleep -Seconds 60
}
