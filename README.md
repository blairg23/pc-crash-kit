# pc-crash-kit

Windows-first CLI to collect and triage crash artifacts (WER, LiveKernelReports, minidumps, event logs).

CLI choice: `argparse` keeps the runtime dependency set minimal and avoids extra install steps on Windows.

## Requirements
- Windows 11
- PowerShell 5.1+
- Python 3.12
- Poetry

## Install
1. `poetry install`

## Quick Start (Stupid Easy)
Use the same command everywhere once you add `scripts/` to PATH.

### 1) One-Time Setup (adds `scripts/` to PATH)
PowerShell:
```powershell
[Environment]::SetEnvironmentVariable("PATH", "D:\\Dropbox\\Projects\\sandboxes\\python\\pc-crash-kit\\scripts;" + [Environment]::GetEnvironmentVariable("PATH","User"), "User")
```

WSL bash:
```bash
echo 'export PATH="/mnt/d/Dropbox/Projects/sandboxes/python/pc-crash-kit/scripts:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### 2) Run (same command in any terminal)
```bash
pc-crash-kit collect --require-admin --strict-access
```

If you are not admin, you will get a UAC prompt and it will re-run elevated.

If the tool prints a "Run this in PS" block, **copy/paste exactly what it prints** into PowerShell.

## One-Command Full Run
Collect, summarize, and doctor in one command:
```powershell
$c = poetry run pc-crash-kit collect --require-admin --strict-access --json | ConvertFrom-Json; poetry run pc-crash-kit summarize $c.output_dir; poetry run pc-crash-kit doctor
```

## What Each Command Does
- `collect`: Copies WER ReportQueue, LiveKernelReports, minidumps, and exports System/Application event logs into `artifacts/<timestamp>/`. Writes `manifest.json` with what was copied or skipped.
- `summarize`: Parses `Report.wer` files, clusters signatures, and produces `summary.json` + `summary.txt`. Also includes `system_info` (OS/GPU/BIOS/CPU) from PowerShell `Get-CimInstance`. Defaults to the latest bundle under `./artifacts`.
- `doctor`: Runs system diagnostics and saves output to the latest bundle under `./artifacts` (if present), otherwise `artifacts/doctor-<timestamp>/`. Uses config defaults, or `--full`/`--minimal` to override, plus per-check flags for extra data.

## Poetry Not Found (Fix Once)
If PowerShell says "poetry is not recognized", run this in PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-poetry-path.ps1
```

To make it permanent for your user:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-poetry-path.ps1 -Persist
```

If you still want to verify the location manually:
```powershell
Get-ChildItem -Path "$env:APPDATA","$env:LOCALAPPDATA" -Filter "poetry.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
```

## Config File (Custom Paths)
Create `pc-crash-kit.toml` in the repo root to override default locations and include custom game dumps.
Custom groups live under `[custom.<group_name>]` and are copied into `artifacts/custom/<group_name>/`.

Example:
```toml
[paths]
wer_queue = "C:\\ProgramData\\Microsoft\\Windows\\WER\\ReportQueue"
livekernel_reports = "C:\\Windows\\LiveKernelReports"
minidump = "C:\\Windows\\Minidump"

[wer]
patterns = ["Kernel_193_*", "Kernel_15e_*", "Kernel_1a8_*"]

[livekernel]
folders = ["WATCHDOG", "NDIS", "USBXHCI", "USBHUB3", "PoW32kWatchdog"]

[custom.arc_raiders]
dirs = [
  "%LOCALAPPDATA%\\PioneerGame\\Saved\\Crashes",
  "%LOCALAPPDATA%\\PioneerGame\\Saved\\Config"
]
globs = [
  "%TEMP%\\**\\*.dmp"
]

[doctor]
systeminfo = true
system_info = true
dxdiag = false
msinfo = false
drivers = false
hotfixes = false
crash_config = false
sfc = false
dism_scan = false
dism_restore = false
```

Doctor reads `[doctor]` from the same config file. You can also pass `--config` to `pc-crash-kit doctor`.

You can also point to a config file explicitly:
```powershell
poetry run pc-crash-kit collect --config C:\path\to\pc-crash-kit.toml --require-admin --strict-access
```

Collect more items and more logs:
```powershell
poetry run pc-crash-kit collect --latest-n 5 --eventlog-hours 48 --require-admin --strict-access
```

Collect different counts for LiveKernelReports and minidumps:
```powershell
poetry run pc-crash-kit collect --latest-n 3 --latest-livekernel 5 --latest-minidump 2 --require-admin --strict-access
```

Include large dumps (over 1 GB) and raise the size limit:
```powershell
poetry run pc-crash-kit collect --include-large-dumps --max-dump-gb 2 --require-admin --strict-access
```

Emit machine-readable JSON for scripting:
```powershell
poetry run pc-crash-kit collect --json --require-admin --strict-access
```

Override WER patterns (repeatable):
```powershell
poetry run pc-crash-kit collect --wer-pattern Kernel_193_* --wer-pattern Kernel_15e_* --require-admin --strict-access
```

Summarize the latest collected bundle (default):
```powershell
poetry run pc-crash-kit summarize
```

Summarize a specific bundle:
```powershell
poetry run pc-crash-kit summarize artifacts\20250205-120000
```

Run doctor checks:
```powershell
poetry run pc-crash-kit doctor
poetry run pc-crash-kit doctor --run-sfc --dism-scan
```

Full and minimal doctor presets:
```powershell
poetry run pc-crash-kit doctor --full
poetry run pc-crash-kit doctor --minimal
```

Enable extra doctor checks explicitly:
```powershell
poetry run pc-crash-kit doctor --dxdiag --drivers --hotfixes
```

## Notes
- Full access requires admin. Use `--require-admin --strict-access` for fail-fast behavior.
- Dumps larger than 1 GB are skipped by default. Skipped files are listed in `manifest.json` under `copy_report.skipped_large`.
- Windows commands used: `wevtutil`, `systeminfo`, PowerShell `Get-CimInstance`, `sfc`, `DISM`.
- `summarize` will parse `sysinfo.txt` and `memory.csv` if present in the bundle, and will include `system_info` output from PowerShell if available.

## PowerShell Helper
The helper script auto-elevates and uses Poetry if available, otherwise falls back to Python.

```powershell
.\scripts\pc-crash-kit.ps1 collect --require-admin --strict-access
```

## Sample summarize output

`artifacts/summary.json` (schema example):
```json
{
  "generated_at": "20250205-120000",
  "bundle_dir": "C:\\path\\to\\artifacts\\20250205-120000",
  "artifact_stats": {
    "wer_report_count": 2,
    "livekernel_files": 3,
    "minidump_files": 1,
    "largest_livekernel_file": {
      "path": "C:\\path\\to\\artifacts\\20250205-120000\\livekernelreports\\WATCHDOG\\WATCHDOG-123.dmp",
      "size": "812.4MB"
    }
  },
  "report_count": 2,
  "signature_counts": [
    {
      "signature": "Sig0=193 Sig1=80e",
      "count": 2
    }
  ],
  "reports": [
    {
      "path": "C:\\path\\to\\artifacts\\20250205-120000\\wer\\Kernel_193_12345\\Report.wer",
      "event_type": "LiveKernelEvent",
      "friendly_event_name": "Windows Hardware Error",
      "sig_values": {
        "0": "193",
        "1": "80e"
      },
      "sig_names": {
        "0": "Code",
        "1": "Parameter 1"
      },
      "ns_values": {
        "0": "BlueScreen"
      },
      "stop_code": "193",
      "dump_file": "C:\\Windows\\LiveKernelReports\\WATCHDOG\\WATCHDOG-123.dmp",
      "report_id": "abcd-1234",
      "problem_signature": "P1: 193"
    }
  ],
  "gpu": [
    {
      "Name": "NVIDIA GeForce RTX 4090",
      "DriverVersion": "31.0.15.5222",
      "DriverDate": "20240110"
    }
  ],
  "os": {
    "Caption": "Microsoft Windows 11 Pro",
    "Version": "10.0.22631",
    "BuildNumber": "22631"
  },
  "manifest": {
    "output_dir": "C:\\path\\to\\artifacts\\20250205-120000",
    "latest_n": 3,
    "eventlog_hours": 24,
    "include_large_dumps": false,
    "max_dump_gb": 1,
    "wer_patterns": ["Kernel_193_*", "Kernel_15e_*", "Kernel_1a8_*"],
    "copy_report": {
      "copied": [],
      "skipped_large": [],
      "missing": []
    }
  }
}
```

`artifacts/summary.txt` (example):
```text
pc-crash-kit summary
Bundle: C:\path\to\artifacts\20250205-120000
Generated: 20250205-120000
WER reports: 2
LiveKernelReports files: 3
Minidump files: 1

Top signatures:
- Sig0=193 Sig1=80e (2)

GPU:
- NVIDIA GeForce RTX 4090 DriverVersion=31.0.15.5222 DriverDate=20240110

OS:
- Caption: Microsoft Windows 11 Pro
- Version: 10.0.22631
- BuildNumber: 22631
```
