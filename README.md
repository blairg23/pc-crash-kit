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

## Usage
Collect crash artifacts into `./artifacts/<timestamp>/`:
```bash
poetry run pc-crash-kit collect
```

Collect more items and more logs:
```bash
poetry run pc-crash-kit collect --latest-n 5 --eventlog-hours 48
```

Include large dumps (over 1 GB) and raise the size limit:
```bash
poetry run pc-crash-kit collect --include-large-dumps --max-dump-gb 2
```

Override WER patterns (repeatable):
```bash
poetry run pc-crash-kit collect --wer-pattern Kernel_193_* --wer-pattern Kernel_15e_*
```

Summarize a collected bundle:
```bash
poetry run pc-crash-kit summarize artifacts/20250205-120000
```

Run doctor checks:
```bash
poetry run pc-crash-kit doctor
poetry run pc-crash-kit doctor --run-sfc --dism-scan
```

## Notes
- Some paths and event log exports require admin. If you are not admin, the tool will warn and skip what it cannot read.
- Dumps larger than 1 GB are skipped by default. Skipped files are listed in `manifest.json` under `copy_report.skipped_large`.
- Windows commands used: `wevtutil`, `wmic`, `systeminfo`, `sfc`, `DISM`.

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
