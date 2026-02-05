# scripts/collect-crash-artifacts.ps1
# Usage examples:
#   powershell -ExecutionPolicy Bypass -File .\scripts\collect-crash-artifacts.ps1
#   powershell -ExecutionPolicy Bypass -File .\scripts\collect-crash-artifacts.ps1 -SinceHours 6 -Zip
#   powershell -ExecutionPolicy Bypass -File .\scripts\collect-crash-artifacts.ps1 -SinceMinutes 45 -OutRoot ".\out" -Zip

[CmdletBinding()]
param(
  [int]$SinceHours = 24,
  [int]$SinceMinutes = 0,
  [string]$OutRoot = ".\out",
  [switch]$CopyDumps = $true,
  [switch]$Zip = $true
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-Dir($path) {
  if (-not (Test-Path $path)) { New-Item -ItemType Directory -Path $path | Out-Null }
}

function Write-Note($path, $text) {
  $text | Out-File -FilePath $path -Encoding UTF8
}

$ts = (Get-Date).ToString("yyyyMMdd-HHmmss")
$base = Join-Path $OutRoot "crash-$ts"
New-Dir $base

$metaDir = Join-Path $base "meta"
$logsDir = Join-Path $base "logs"
$dumpDir = Join-Path $base "dumps"
$werDir  = Join-Path $base "wer"
New-Dir $metaDir
New-Dir $logsDir
New-Dir $dumpDir
New-Dir $werDir

$since = if ($SinceMinutes -gt 0) { (Get-Date).AddMinutes(-1 * $SinceMinutes) } else { (Get-Date).AddHours(-1 * $SinceHours) }
Write-Note (Join-Path $base "README.txt") @"
Crash capture created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Since: $since
Machine: $env:COMPUTERNAME
User: $env:USERNAME

What is inside:
- logs\  JSON exports from System, Application, WER, and ReliabilityMonitor
- dumps\ Minidump, MEMORY.DMP (if present), LiveKernelReports (if present)
- wer\   Windows Error Reporting report folders (if present)
- meta\  systeminfo, driver inventory, gpu inventory, basic health checks
"@

# -------------------------
# Meta snapshots
# -------------------------
try { systeminfo /FO LIST > (Join-Path $metaDir "systeminfo.txt") } catch {}
try { Get-ComputerInfo | Out-File (Join-Path $metaDir "Get-ComputerInfo.txt") -Encoding UTF8 } catch {}
try { driverquery /V /FO CSV > (Join-Path $metaDir "driverquery.csv") } catch {}
try { Get-CimInstance Win32_VideoController | Format-List * | Out-File (Join-Path $metaDir "video_controllers.txt") -Encoding UTF8 } catch {}
try { Get-CimInstance Win32_OperatingSystem | Format-List * | Out-File (Join-Path $metaDir "os.txt") -Encoding UTF8 } catch {}
try { Get-CimInstance Win32_ComputerSystem | Format-List * | Out-File (Join-Path $metaDir "computer_system.txt") -Encoding UTF8 } catch {}
try { Get-CimInstance Win32_Processor | Format-List * | Out-File (Join-Path $metaDir "cpu.txt") -Encoding UTF8 } catch {}
try { Get-PhysicalDisk | Format-Table -AutoSize | Out-File (Join-Path $metaDir "physical_disks.txt") -Encoding UTF8 } catch {}
try { Get-Disk | Format-Table -AutoSize | Out-File (Join-Path $metaDir "disks.txt") -Encoding UTF8 } catch {}
try { Get-Volume | Format-Table -AutoSize | Out-File (Join-Path $metaDir "volumes.txt") -Encoding UTF8 } catch {}

# Optional but useful
try { dxdiag /t (Join-Path $metaDir "dxdiag.txt") | Out-Null } catch {}
# msinfo32 can take a bit and sometimes hangs on some systems, so wrap tightly
try {
  $msinfo = Join-Path $metaDir "msinfo32.nfo"
  Start-Process -FilePath "msinfo32.exe" -ArgumentList "/nfo `"$msinfo`"" -Wait -NoNewWindow
} catch {}

# Basic health checks (fast)
try { chkdsk > (Join-Path $metaDir "chkdsk_last_run_hint.txt") } catch {}
try { Get-WinEvent -FilterHashtable @{LogName="Microsoft-Windows-WER-SystemErrorReporting/Operational"; StartTime=$since} -ErrorAction SilentlyContinue | Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message | ConvertTo-Json -Depth 4 > (Join-Path $logsDir "wer_systemerrorreporting.json") } catch {}

# -------------------------
# Targeted event logs
# -------------------------
# System log IDs commonly relevant to black-screen, driver reset, bugcheck, unexpected reboot
$systemIds = @(41, 6008, 1001, 13, 14, 161, 4101, 219, 7000, 7001, 7031, 7045)
# Application log IDs commonly relevant to app crash, hang, WER
$appIds = @(1000, 1001, 1002, 1005, 1026)

function Export-EventsJson($logName, $ids, $outPath) {
  $events = Get-WinEvent -FilterHashtable @{LogName=$logName; Id=$ids; StartTime=$since} -ErrorAction SilentlyContinue |
    Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message
  $events | ConvertTo-Json -Depth 4 | Out-File $outPath -Encoding UTF8
}

Export-EventsJson "System" $systemIds (Join-Path $logsDir "system_events.json")
Export-EventsJson "Application" $appIds (Join-Path $logsDir "application_events.json")

# Grab recent display driver resets even if ID filtering misses variants
try {
  Get-WinEvent -FilterHashtable @{LogName="System"; StartTime=$since} -ErrorAction SilentlyContinue |
    Where-Object { $_.ProviderName -match "Display|nvlddmkm|amdkmdag|WHEA|Kernel-Power" } |
    Select-Object TimeCreated, Id, LevelDisplayName, ProviderName, Message |
    ConvertTo-Json -Depth 4 > (Join-Path $logsDir "system_provider_focus.json")
} catch {}

# Reliability Monitor records (often contains "Hardware error" LiveKernelEvent, etc.)
try {
  $rels = Get-CimInstance -Namespace "root\cimv2" -ClassName "Win32_ReliabilityRecords" -ErrorAction SilentlyContinue |
    Where-Object { $_.TimeGenerated -ge $since } |
    Select-Object TimeGenerated, SourceName, ProductName, EventIdentifier, Message
  $rels | ConvertTo-Json -Depth 4 | Out-File (Join-Path $logsDir "reliability_records.json") -Encoding UTF8
} catch {}

# -------------------------
# Crash artifacts
# -------------------------
if ($CopyDumps) {
  $pathsToCopy = @(
    "C:\Windows\Minidump",
    "C:\Windows\MEMORY.DMP",
    "C:\Windows\LiveKernelReports"
  )

  foreach ($p in $pathsToCopy) {
    if (Test-Path $p) {
      if ((Get-Item $p).PSIsContainer) {
        # copy last 20 files from folder
        Get-ChildItem $p -File -ErrorAction SilentlyContinue |
          Sort-Object LastWriteTime -Descending |
          Select-Object -First 20 |
          ForEach-Object {
            Copy-Item $_.FullName -Destination (Join-Path $dumpDir $_.Name) -Force -ErrorAction SilentlyContinue
          }
      } else {
        Copy-Item $p -Destination (Join-Path $dumpDir (Split-Path $p -Leaf)) -Force -ErrorAction SilentlyContinue
      }
    }
  }

  # Windows Error Reporting crash folders (can be huge, so keep it recent)
  $werRoots = @(
    "C:\ProgramData\Microsoft\Windows\WER\ReportArchive",
    "C:\ProgramData\Microsoft\Windows\WER\ReportQueue"
  )

  foreach ($wr in $werRoots) {
    if (Test-Path $wr) {
      Get-ChildItem $wr -Directory -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 15 |
        ForEach-Object {
          $dest = Join-Path $werDir $_.Name
          Copy-Item $_.FullName -Destination $dest -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
  }
}

# -------------------------
# Zip output
# -------------------------
if ($Zip) {
  $zipPath = Join-Path $OutRoot "crash-$ts.zip"
  if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
  Compress-Archive -Path $base\* -DestinationPath $zipPath -Force
  Write-Host "Created: $zipPath"
} else {
  Write-Host "Created: $base"
}
