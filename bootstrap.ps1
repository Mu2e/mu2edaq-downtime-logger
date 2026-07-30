<#
.SYNOPSIS
    Bootstrap mu2edaq-downtime-logger on Windows (PowerShell port of
    bootstrap.sh): create/update the venv and install dependencies + the package.

.PARAMETER Postgres
    Also install psycopg2-binary (PostgreSQL backend support).

.PARAMETER Dev
    Also install dev/test dependencies (pytest, pytest-qt).

.PARAMETER Recreate
    Delete and recreate the venv from scratch.
#>
[CmdletBinding()]
param(
    [switch]$Postgres,
    [switch]$Dev,
    [switch]$Recreate
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here
$Venv = Join-Path $Here 'venv'

# Prefer 'python'; fall back to the py launcher ('python3' on Windows is the
# Microsoft Store alias stub, so it is not used here).
$Python = $env:PYTHON
if (-not $Python) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $Python = 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py' }
    else { Write-Error 'Python 3.9+ not found on PATH. Install it first.'; exit 1 }
}

if ($Recreate -and (Test-Path $Venv)) { Remove-Item -Recurse -Force $Venv }
if (-not (Test-Path $Venv)) { & $Python -m venv $Venv }

$VenvPy = Join-Path $Venv 'Scripts\python.exe'
& $VenvPy -m pip install --upgrade pip | Out-Null
& $VenvPy -m pip install -e .
if ($Postgres) { & $VenvPy -m pip install psycopg2-binary }
if ($Dev)      { & $VenvPy -m pip install pytest pytest-qt }

# Install the discovery sibling if checked out next to us (best effort).
if (Test-Path '..\mu2edaq-discovery') { & $VenvPy -m pip install -e '..\mu2edaq-discovery' }

Write-Host ''
Write-Host 'Bootstrap complete. Start with:  .\start-mu2edaq-downtime-logger.ps1'
