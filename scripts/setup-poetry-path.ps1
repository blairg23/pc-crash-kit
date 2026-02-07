[CmdletBinding()]
param(
    [switch]$Persist
)

$poetryExe = Get-ChildItem -Path "$env:APPDATA","$env:LOCALAPPDATA" -Filter "poetry.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $poetryExe) {
    Write-Error "poetry.exe not found under APPDATA or LOCALAPPDATA. Install Poetry first."
    exit 1
}

$poetryDir = $poetryExe.Directory.FullName
$env:PATH = "$poetryDir;$env:PATH"

if ($Persist) {
    $current = [Environment]::GetEnvironmentVariable("PATH", "User")
    if ($null -eq $current) {
        $current = ""
    }
    if ($current -notlike "*$poetryDir*") {
        [Environment]::SetEnvironmentVariable("PATH", "$poetryDir;$current", "User")
    }
    Write-Host "Added to USER PATH: $poetryDir"
} else {
    Write-Host "Added to current session PATH: $poetryDir"
}

poetry --version
