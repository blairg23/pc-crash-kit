param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDir,
    [switch]$SystemInfo,
    [switch]$SystemSnapshot,
    [switch]$DxDiag,
    [switch]$MsInfo,
    [switch]$Drivers,
    [switch]$Hotfixes,
    [switch]$CrashConfig,
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

function Write-JsonFile {
    param(
        [string]$Name,
        [object]$Value,
        [string]$OutputFile,
        [string[]]$Cmd = @()
    )
    $path = Join-Path $OutputDir $OutputFile
    $json = $Value | ConvertTo-Json -Depth 6
    Set-Content -Path $path -Value $json -Encoding UTF8
    return [pscustomobject]@{
        name = $Name
        cmd = $Cmd
        returncode = 0
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

if ($SystemInfo) {
    $result.commands += Invoke-Capture "systeminfo" @("systeminfo") "systeminfo.txt"
}

if ($SystemSnapshot) {
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
}

if ($DxDiag) {
    $dxPath = Join-Path $OutputDir "dxdiag.txt"
    $dxOut = & dxdiag /t $dxPath 2>&1 | Out-String
    $dxCode = $LASTEXITCODE
    if ($dxCode -ne 0) {
        $result.errors += "dxdiag failed: $dxOut"
    }
    $result.commands += [pscustomobject]@{
        name = "dxdiag"
        cmd = @("dxdiag", "/t", $dxPath)
        returncode = $dxCode
        output_file = $dxPath
    }
}

if ($MsInfo) {
    $msPath = Join-Path $OutputDir "msinfo.txt"
    $msOut = & msinfo32 /report $msPath 2>&1 | Out-String
    $msCode = $LASTEXITCODE
    if ($msCode -ne 0) {
        $result.errors += "msinfo32 failed: $msOut"
    }
    $result.commands += [pscustomobject]@{
        name = "msinfo32"
        cmd = @("msinfo32", "/report", $msPath)
        returncode = $msCode
        output_file = $msPath
    }
}

if ($Drivers) {
    $result.commands += Invoke-Capture "drivers" @("driverquery", "/v", "/fo", "csv") "drivers.csv"
}

if ($Hotfixes) {
    try {
        $items = Get-HotFix | Sort-Object InstalledOn -Descending | Select-Object HotFixID,InstalledOn,Description,InstalledBy
        $result.commands += Write-JsonFile "hotfixes" $items "hotfixes.json" @("Get-HotFix")
    } catch {
        $result.errors += "Get-HotFix failed: $($_.Exception.Message)"
    }
}

if ($CrashConfig) {
    $result.commands += Invoke-Capture "crash_config" @("reg", "query", "HKLM\\SYSTEM\\CurrentControlSet\\Control\\CrashControl", "/s") "crash_config.txt"
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
