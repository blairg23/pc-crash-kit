param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDir,
    [switch]$RunSfc,
    [switch]$DismScan,
    [switch]$DismRestore
)

$ErrorActionPreference = "SilentlyContinue"

function Test-IsAdmin {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Invoke-Capture {
    param(
        [string]$Name,
        [string[]]$Cmd,
        [string]$OutputFile
    )
    $exe = $Cmd[0]
    $args = @()
    if ($Cmd.Length -gt 1) {
        $args = $Cmd[1..($Cmd.Length - 1)]
    }
    $out = & $exe @args 2>&1 | Out-String
    $code = $LASTEXITCODE
    $path = Join-Path $OutputDir $OutputFile
    Set-Content -Path $path -Value $out -Encoding UTF8
    return [pscustomobject]@{
        name = $Name
        cmd = $Cmd
        returncode = $code
        output_file = $path
    }
}

if (-not (Test-Path -Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$isAdmin = Test-IsAdmin
$result = [ordered]@{
    output_dir = $OutputDir
    is_admin = $isAdmin
    commands = @()
    skipped = @()
    errors = @()
}

$result.commands += Invoke-Capture "systeminfo" @("systeminfo") "systeminfo.txt"

$scriptPath = Join-Path $PSScriptRoot "system-info.ps1"
if (Test-Path $scriptPath) {
    $sysInfoPath = Join-Path $OutputDir "system_info.json"
    $sysOut = & $scriptPath -OutputPath $sysInfoPath 2>&1 | Out-String
    $sysCode = $LASTEXITCODE
    if ($sysCode -ne 0) {
        $result.errors += "system-info.ps1 failed: $sysOut"
    }
    $result.commands += [pscustomobject]@{
        name = "system_info"
        cmd = @($scriptPath, "-OutputPath", $sysInfoPath)
        returncode = $sysCode
        output_file = $sysInfoPath
    }
} else {
    $result.errors += "system-info.ps1 not found."
}

if ($RunSfc) {
    if ($isAdmin) {
        $result.commands += Invoke-Capture "sfc" @("sfc", "/scannow") "sfc.txt"
    } else {
        $result.skipped += "sfc requires admin"
    }
}

if ($DismScan) {
    if ($isAdmin) {
        $result.commands += Invoke-Capture "dism_scan" @("DISM", "/Online", "/Cleanup-Image", "/ScanHealth") "dism_scan.txt"
    } else {
        $result.skipped += "DISM /ScanHealth requires admin"
    }
}

if ($DismRestore) {
    if ($isAdmin) {
        $result.commands += Invoke-Capture "dism_restore" @("DISM", "/Online", "/Cleanup-Image", "/RestoreHealth") "dism_restore.txt"
    } else {
        $result.skipped += "DISM /RestoreHealth requires admin"
    }
}

Write-Output ($result | ConvertTo-Json -Depth 6)
