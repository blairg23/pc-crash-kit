from __future__ import annotations

import json
import logging
from pathlib import Path

from .utils import ensure_dir, is_admin, is_windows, run_cmd, timestamp_now

logger = logging.getLogger(__name__)


def _run_and_save(output_dir: Path, name: str, cmd: list[str], filename: str) -> dict:
    result = run_cmd(cmd, capture=True, check=False)
    out_path = output_dir / filename
    combined = (result.stdout or "") + ("\n" if result.stderr else "") + (result.stderr or "")
    out_path.write_text(combined, encoding="utf-8", errors="ignore")
    return {
        "name": name,
        "cmd": cmd,
        "returncode": result.returncode,
        "output_file": str(out_path),
    }


def doctor(
    output_dir: Path | None,
    run_sfc: bool = False,
    dism_scan: bool = False,
    dism_restore: bool = False,
) -> dict:
    if output_dir is None:
        output_dir = Path("artifacts") / f"doctor-{timestamp_now()}"
    ensure_dir(output_dir)

    result: dict = {
        "output_dir": str(output_dir),
        "is_admin": is_admin(),
        "commands": [],
        "skipped": [],
    }

    if not is_windows():
        result["skipped"].append("Not running on Windows")
        return result

    baseline_cmds = [
        ("systeminfo", ["systeminfo"], "systeminfo.txt"),
        (
            "wmic_os",
            ["wmic", "os", "get", "Caption,Version,BuildNumber", "/format:list"],
            "wmic_os.txt",
        ),
        (
            "wmic_bios",
            ["wmic", "bios", "get", "Manufacturer,SMBIOSBIOSVersion,ReleaseDate", "/format:list"],
            "wmic_bios.txt",
        ),
        (
            "wmic_cpu",
            ["wmic", "cpu", "get", "Name,NumberOfCores,NumberOfLogicalProcessors", "/format:list"],
            "wmic_cpu.txt",
        ),
        (
            "wmic_computersystem",
            ["wmic", "computersystem", "get", "Manufacturer,Model,TotalPhysicalMemory,HypervisorPresent", "/format:list"],
            "wmic_computersystem.txt",
        ),
        (
            "wmic_gpu",
            ["wmic", "path", "Win32_VideoController", "get", "Name,DriverVersion", "/format:list"],
            "wmic_gpu.txt",
        ),
    ]

    for name, cmd, filename in baseline_cmds:
        result["commands"].append(_run_and_save(output_dir, name, cmd, filename))

    if run_sfc:
        if result["is_admin"]:
            result["commands"].append(
                _run_and_save(output_dir, "sfc", ["sfc", "/scannow"], "sfc.txt")
            )
        else:
            result["skipped"].append("sfc requires admin")

    if dism_scan:
        if result["is_admin"]:
            result["commands"].append(
                _run_and_save(
                    output_dir,
                    "dism_scan",
                    ["DISM", "/Online", "/Cleanup-Image", "/ScanHealth"],
                    "dism_scan.txt",
                )
            )
        else:
            result["skipped"].append("DISM /ScanHealth requires admin")

    if dism_restore:
        if result["is_admin"]:
            result["commands"].append(
                _run_and_save(
                    output_dir,
                    "dism_restore",
                    ["DISM", "/Online", "/Cleanup-Image", "/RestoreHealth"],
                    "dism_restore.txt",
                )
            )
        else:
            result["skipped"].append("DISM /RestoreHealth requires admin")

    (output_dir / "doctor_manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    return result
