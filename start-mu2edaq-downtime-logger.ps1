<#
.SYNOPSIS
    Start mu2edaq-downtime-logger on Windows (PowerShell port of
    start-mu2edaq-downtime-logger.sh): bootstrap the venv if needed, then run
    the app in the background (or foreground) with a pid file.

.PARAMETER Config
    Path to YAML config (default: config\local.yaml).

.PARAMETER LogLevel
    Log level: DEBUG, INFO, WARNING, ERROR (default: INFO).

.PARAMETER LogFile
    Redirect output to FILE.

.PARAMETER Foreground
    Run in the foreground instead of background.

.PARAMETER ExtraArgs
    Any remaining arguments are passed directly to the application.
#>
[CmdletBinding()]
param(
    [string]$Config,
    [string]$LogLevel = 'INFO',
    [string]$LogFile,
    [switch]$Foreground,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ExtraArgs
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$Venv = Join-Path $ScriptDir 'venv'
$PidFile = Join-Path $ScriptDir 'mu2edaq-downtime-logger.pid'
if (-not $LogFile) { $LogFile = Join-Path $ScriptDir 'mu2edaq-downtime-logger.log' }
if (-not $Config)  { $Config  = Join-Path $ScriptDir 'config\local.yaml' }

$AppExe = Join-Path $Venv 'Scripts\mu2edaq-downtime-logger.exe'
if (-not (Test-Path $AppExe)) {
    Write-Host '--- Virtual environment not found; running bootstrap first.'
    & (Join-Path $ScriptDir 'bootstrap.ps1')
}

function Test-ProcessAlive([int]$ProcId) {
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

if (Test-Path $PidFile) {
    $old = (Get-Content $PidFile -Raw).Trim()
    if ($old -match '^\d+$' -and (Test-ProcessAlive ([int]$old))) {
        Write-Error "mu2edaq-downtime-logger is already running (PID $old)."
        exit 1
    }
    Write-Host "Removing stale PID file (PID $old no longer running)."
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

$argList = @('--config', $Config, '--log-level', $LogLevel)
if ($ExtraArgs) { $argList += $ExtraArgs }

if ($Foreground) {
    & $AppExe @argList
    exit $LASTEXITCODE
}

Write-Host '--- Starting mu2edaq-downtime-logger in background'
Write-Host "    Config:    $Config"
Write-Host "    Log:       $LogFile"
Write-Host "    PID file:  $PidFile"
$proc = Start-Process -FilePath $AppExe -ArgumentList $argList -WorkingDirectory $ScriptDir `
    -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err" `
    -WindowStyle Hidden -PassThru
Set-Content -Path $PidFile -Value $proc.Id -Encoding ascii
Write-Host "--- Started with PID $($proc.Id)"
