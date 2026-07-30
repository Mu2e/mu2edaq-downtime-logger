<#
.SYNOPSIS
    Stop mu2edaq-downtime-logger cleanly on Windows (PowerShell port of
    stop-mu2edaq-downtime-logger.sh): graceful close, escalating to a forced
    kill after a timeout, and clean up the pid file.

.PARAMETER Timeout
    Seconds to wait for graceful shutdown (default: 10).

.PARAMETER Force
    Kill immediately without attempting graceful shutdown.
#>
[CmdletBinding()]
param(
    [int]$Timeout = 10,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir 'mu2edaq-downtime-logger.pid'

function Test-ProcessAlive([int]$ProcId) {
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}

if (-not (Test-Path $PidFile)) {
    Write-Host "No PID file found at $PidFile -- application may not be running."
    exit 0
}

$ProcId = [int]((Get-Content $PidFile -Raw).Trim())
if (-not (Test-ProcessAlive $ProcId)) {
    Write-Host "PID $ProcId not running; cleaning up stale PID file."
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

if ($Force) {
    Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
} else {
    $proc = Get-Process -Id $ProcId -ErrorAction SilentlyContinue
    if ($proc) { $proc.CloseMainWindow() | Out-Null }
    for ($i = 0; $i -lt $Timeout; $i++) {
        if (-not (Test-ProcessAlive $ProcId)) { break }
        Start-Sleep -Seconds 1
    }
    if (Test-ProcessAlive $ProcId) {
        Write-Host "did not exit within ${Timeout}s; forcing"
        Stop-Process -Id $ProcId -Force -ErrorAction SilentlyContinue
    }
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host 'mu2edaq-downtime-logger stopped.'
