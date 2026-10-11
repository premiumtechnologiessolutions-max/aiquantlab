$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$EnvironmentRoot = Join-Path $ProjectRoot ".venv312"
$PythonPath = Join-Path $EnvironmentRoot "Scripts\python.exe"

if (-not (Test-Path $PythonPath)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        Write-Host "Python Launcher is missing. Install Python 3.12 from python.org, then run this file again." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }

    Write-Host "First start: creating a dedicated Python 3.12 environment..." -ForegroundColor Cyan
    & py -3.12 -m venv $EnvironmentRoot

    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $PythonPath)) {
        Write-Host "Python 3.12 was not found. Install Python 3.12 (not 3.13/3.14), then retry." -ForegroundColor Red
        Read-Host "Press Enter to close"
        exit 1
    }

    Write-Host "Installing AI Quant Lab and its runtime dependencies..." -ForegroundColor Cyan
    & $PythonPath -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "Could not upgrade pip." }
    & $PythonPath -m pip install -e $ProjectRoot
    if ($LASTEXITCODE -ne 0) { throw "Could not install AI Quant Lab." }
}

$PythonVersion = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($PythonVersion.Trim() -ne "3.12") {
    Write-Host "The .venv312 folder is not Python 3.12. Rename it and run this starter again." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "AI Quant Lab - MT5 Demo connection" -ForegroundColor Cyan
Write-Host "Leave login empty to use the account already open in your local MT5 terminal."

$TerminalPath = Read-Host "terminal64.exe path (Enter for auto-discovery)"
$Login = Read-Host "MT5 Demo login (Enter to use the open terminal account)"
$Server = Read-Host "Broker demo server (Enter to use the open terminal account)"

if ($TerminalPath) { $env:AI_QUANT_MT5_TERMINAL_PATH = $TerminalPath }
if ($Login) { $env:AI_QUANT_MT5_LOGIN = $Login }
if ($Server) { $env:AI_QUANT_MT5_SERVER = $Server }

if ($Login) {
    $SecurePassword = Read-Host "MT5 Demo password" -AsSecureString
    $Credential = New-Object System.Management.Automation.PSCredential("unused", $SecurePassword)
    $env:AI_QUANT_MT5_PASSWORD = $Credential.GetNetworkCredential().Password
}

$env:AI_QUANT_ENABLE_DEMO_ORDERS = "false"

try {
    Set-Location $ProjectRoot
    & $PythonPath -X utf8 -m ai_quant_lab voice-dashboard --pairs EURUSD --timeframe M15
}
finally {
    Remove-Item Env:AI_QUANT_MT5_PASSWORD -ErrorAction SilentlyContinue
    Remove-Item Env:AI_QUANT_MT5_LOGIN -ErrorAction SilentlyContinue
    Remove-Item Env:AI_QUANT_MT5_SERVER -ErrorAction SilentlyContinue
    Remove-Item Env:AI_QUANT_MT5_TERMINAL_PATH -ErrorAction SilentlyContinue
}
