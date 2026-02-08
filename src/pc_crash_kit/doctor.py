from __future__ import annotations

import json
import logging
from pathlib import Path

from .utils import ensure_dir, is_admin, is_windows, run_cmd, timestamp_now

logger = logging.getLogger(__name__)


def _run_doctor_script(
    output_dir: Path,
    run_sfc: bool,
    dism_scan: bool,
    dism_restore: bool,
) -> dict:
    script = Path(__file__).resolve().parents[2] / "scripts" / "doctor-checks.ps1"
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputDir",
        str(output_dir),
    ]
    if run_sfc:
        cmd.append("-RunSfc")
    if dism_scan:
        cmd.append("-DismScan")
    if dism_restore:
        cmd.append("-DismRestore")

    result = run_cmd(cmd, capture=True, check=False)
    raw = (result.stdout or "").strip()
    if result.returncode != 0:
        logger.warning("doctor-checks.ps1 failed: %s", (result.stderr or "").strip())
    if not raw:
        return {
            "output_dir": str(output_dir),
            "is_admin": is_admin(),
            "commands": [],
            "skipped": [],
            "errors": ["doctor-checks.ps1 returned no output"],
            "stderr": (result.stderr or "").strip(),
        }
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        logger.warning("Failed to parse doctor-checks.ps1 JSON output.")
    return {
        "output_dir": str(output_dir),
        "is_admin": is_admin(),
        "commands": [],
        "skipped": [],
        "errors": ["doctor-checks.ps1 returned invalid JSON"],
        "raw": raw[:500],
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

    if not is_windows():
        result = {
            "output_dir": str(output_dir),
            "is_admin": is_admin(),
            "commands": [],
            "skipped": ["Not running on Windows"],
        }
        return result

    result = _run_doctor_script(output_dir, run_sfc, dism_scan, dism_restore)
    if "output_dir" not in result:
        result["output_dir"] = str(output_dir)

    (output_dir / "doctor_manifest.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    return result
