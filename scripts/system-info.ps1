param(
    [string]$OutputPath = "",
    [switch]$Pretty
)

$ErrorActionPreference = "SilentlyContinue"

function Convert-DateValue {
    param([object]$Value)
    if ($null -eq $Value) { return $null }
    if ($Value -is [datetime]) { return $Value.ToString("o") }
    try {
        return [System.Management.ManagementDateTimeConverter]::ToDateTime($Value).ToString("o")
    } catch {
        return [string]$Value
    }
}

$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$bios = Get-CimInstance Win32_BIOS -ErrorAction SilentlyContinue
$cpu = Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue
$cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
$gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue

$cpuInfo = @()
if ($cpu) {
    $cpuInfo = $cpu | ForEach-Object {
        [pscustomobject]@{
            Name = $_.Name
            Manufacturer = $_.Manufacturer
            NumberOfCores = $_.NumberOfCores
            NumberOfLogicalProcessors = $_.NumberOfLogicalProcessors
            MaxClockSpeed = $_.MaxClockSpeed
            VirtualizationFirmwareEnabled = $_.VirtualizationFirmwareEnabled
            VMMonitorModeExtensions = $_.VMMonitorModeExtensions
            SecondLevelAddressTranslationExtensions = $_.SecondLevelAddressTranslationExtensions
        }
    }
}

$gpuInfo = @()
if ($gpus) {
    $gpuInfo = $gpus | ForEach-Object {
        [pscustomobject]@{
            Name = $_.Name
            DriverVersion = $_.DriverVersion
            DriverDate = Convert-DateValue $_.DriverDate
            PNPDeviceID = $_.PNPDeviceID
            AdapterRAM = $_.AdapterRAM
            VideoProcessor = $_.VideoProcessor
        }
    }
}

$osInfo = $null
if ($os) {
    $osInfo = [pscustomobject]@{
        Caption = $os.Caption
        Version = $os.Version
        BuildNumber = $os.BuildNumber
        OSArchitecture = $os.OSArchitecture
        InstallDate = Convert-DateValue $os.InstallDate
        LastBootUpTime = Convert-DateValue $os.LastBootUpTime
        SerialNumber = $os.SerialNumber
        CSName = $os.CSName
    }
}

$biosInfo = $null
if ($bios) {
    $biosInfo = [pscustomobject]@{
        Manufacturer = $bios.Manufacturer
        SMBIOSBIOSVersion = $bios.SMBIOSBIOSVersion
        ReleaseDate = Convert-DateValue $bios.ReleaseDate
        SerialNumber = $bios.SerialNumber
    }
}

$csInfo = $null
if ($cs) {
    $csInfo = [pscustomobject]@{
        Manufacturer = $cs.Manufacturer
        Model = $cs.Model
        TotalPhysicalMemory = $cs.TotalPhysicalMemory
        HypervisorPresent = $cs.HypervisorPresent
        SystemType = $cs.SystemType
    }
}

$virtualization = [pscustomobject]@{
    HypervisorPresent = $cs.HypervisorPresent
    VirtualizationFirmwareEnabled = $null
    VMMonitorModeExtensions = $null
    SecondLevelAddressTranslationExtensions = $null
}
if ($cpu) {
    $firstCpu = $cpu | Select-Object -First 1
    $virtualization.VirtualizationFirmwareEnabled = $firstCpu.VirtualizationFirmwareEnabled
    $virtualization.VMMonitorModeExtensions = $firstCpu.VMMonitorModeExtensions
    $virtualization.SecondLevelAddressTranslationExtensions = $firstCpu.SecondLevelAddressTranslationExtensions
}

$payload = [pscustomobject]@{
    collected_at = (Get-Date).ToString("o")
    os = $osInfo
    bios = $biosInfo
    cpu = $cpuInfo
    computer_system = $csInfo
    gpu = $gpuInfo
    virtualization = $virtualization
}

if ($Pretty) {
    $json = $payload | ConvertTo-Json -Depth 6
} else {
    $json = $payload | ConvertTo-Json -Depth 6 -Compress
}

if ($OutputPath) {
    $dir = Split-Path -Path $OutputPath -Parent
    if ($dir -and -not (Test-Path -Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Set-Content -Path $OutputPath -Value $json -Encoding UTF8
}

Write-Output $json
