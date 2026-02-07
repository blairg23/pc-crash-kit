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


def _run_system_info(output_dir: Path) -> dict:
    script = Path(__file__).resolve().parents[2] / "scripts" / "system-info.ps1"
    out_path = output_dir / "system_info.json"
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputPath",
        str(out_path),
    ]
    result = run_cmd(cmd, capture=True, check=False)
    if result.returncode != 0:
        logger.warning("system-info.ps1 failed: %s", result.stderr.strip())
    return {
        "name": "system_info",
        "cmd": cmd,
        "returncode": result.returncode,
        "output_file": str(out_path),
        "stderr": (result.stderr or "").strip(),
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
    ]

    for name, cmd, filename in baseline_cmds:
        result["commands"].append(_run_and_save(output_dir, name, cmd, filename))

    result["commands"].append(_run_system_info(output_dir))

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
