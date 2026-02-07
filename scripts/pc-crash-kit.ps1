[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

function Test-IsAdmin {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Get-Runner {
    if (Get-Command poetry -ErrorAction SilentlyContinue) {
        return @{ Type = "poetry"; Cmd = "poetry run pc-crash-kit" }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Type = "python"; Cmd = "python -m pc_crash_kit.cli" }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Type = "py"; Cmd = "py -3.12 -m pc_crash_kit.cli" }
    }
    return $null
}

$runner = Get-Runner
if ($null -eq $runner) {
    Write-Error "No runner found. Install Python 3.12 or Poetry."
    exit 127
}

if (-not (Test-IsAdmin)) {
    $escapedArgs = $Args | ForEach-Object { "'" + ($_ -replace "'", "''") + "'" }
    $argString = $escapedArgs -join " "
    if ($runner.Type -eq "poetry") {
        $cmd = "cd '$repo'; $($runner.Cmd) $argString"
    } else {
        $cmd = "cd '$repo'; `$env:PYTHONPATH='$repo\\src'; $($runner.Cmd) $argString"
    }
    Start-Process PowerShell -Verb RunAs -WorkingDirectory $repo -ArgumentList "-NoExit", "-Command", $cmd
    exit 0
}

Set-Location -Path $repo
if ($runner.Type -eq "poetry") {
    & poetry run pc-crash-kit @Args
} else {
    $env:PYTHONPATH = "$repo\src"
    if ($runner.Type -eq "python") {
        & python -m pc_crash_kit.cli @Args
    } else {
        & py -3.12 -m pc_crash_kit.cli @Args
    }
}
exit $LASTEXITCODE
