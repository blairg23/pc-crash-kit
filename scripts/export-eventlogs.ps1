[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDir,
    [int]$Hours = 24
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$ms = [int]($Hours * 3600 * 1000)
$query = "*[System[TimeCreated[timediff(@SystemTime) <= $ms]]]"

wevtutil epl System (Join-Path $OutputDir "System.evtx") /q:$query | Out-Null
wevtutil epl Application (Join-Path $OutputDir "Application.evtx") /q:$query | Out-Null
