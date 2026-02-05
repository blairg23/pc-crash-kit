from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

from .utils import (
    CopyReport,
    ensure_dir,
    is_admin,
    is_windows,
    run_cmd,
    timestamp_now,
    copy_dir_with_limit,
    copy_file_with_limit,
)

logger = logging.getLogger(__name__)

WER_QUEUE = Path(r"C:\ProgramData\Microsoft\Windows\WER\ReportQueue")
LIVE_KERNEL = Path(r"C:\Windows\LiveKernelReports")
MINIDUMP = Path(r"C:\Windows\Minidump")

WER_PATTERNS = [
    "Kernel_193_*",
    "Kernel_15e_*",
    "Kernel_1a8_*",
]

LIVE_KERNEL_FOLDERS = [
    "WATCHDOG",
    "NDIS",
    "USBXHCI",
    "USBHUB3",
    "PoW32kWatchdog",
]

DEFAULT_LATEST_N = 3
DEFAULT_MAX_DUMP_GB = 1
DEFAULT_EVENTLOG_HOURS = 24


def _sorted_by_mtime(paths: Iterable[Path]) -> list[Path]:
    def _mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime if path.exists() else 0.0
        except OSError:
            return 0.0

    return sorted(paths, key=_mtime)


def find_latest_dirs(base: Path, patterns: list[str], latest_n: int) -> list[Path]:
    if not base.exists():
        return []
    matches: list[Path] = []
    for pat in patterns:
        matches.extend([p for p in base.glob(pat) if p.is_dir()])
    ordered = _sorted_by_mtime(matches)
    return ordered[-latest_n:]


def find_latest_files(base: Path, latest_n: int) -> list[Path]:
    if not base.exists():
        return []
    files = [p for p in base.iterdir() if p.is_file()]
    ordered = _sorted_by_mtime(files)
    return ordered[-latest_n:]


def find_latest_file_in_subdir(base: Path, subdir: str, latest_n: int) -> list[Path]:
    folder = base / subdir
    if not folder.exists():
        return []
    files = [p for p in folder.iterdir() if p.is_file()]
    ordered = _sorted_by_mtime(files)
    return ordered[-latest_n:] if ordered else []


def export_event_logs(dest_dir: Path, hours: int) -> list[str]:
    ensure_dir(dest_dir)
    outputs = []
    if not is_windows():
        logger.warning("Not running on Windows, skipping event log export.")
        return outputs

    query_ms = hours * 3600 * 1000
    query = f"*[System[TimeCreated[timediff(@SystemTime) <= {query_ms}]]]"
    logs = {
        "System": dest_dir / "System.evtx",
        "Application": dest_dir / "Application.evtx",
    }

    for log_name, out_path in logs.items():
        cmd = ["wevtutil", "epl", log_name, str(out_path), f"/q:{query}"]
        result = run_cmd(cmd, capture=True, check=False)
        if result.returncode != 0:
            logger.warning("Failed to export %s log: %s", log_name, result.stderr.strip())
        else:
            outputs.append(str(out_path))
    return outputs


def collect(
    output_dir: Path | None,
    latest_n: int = DEFAULT_LATEST_N,
    hours: int = DEFAULT_EVENTLOG_HOURS,
    include_large_dumps: bool = False,
    max_dump_gb: int = DEFAULT_MAX_DUMP_GB,
    wer_patterns: list[str] | None = None,
) -> dict:
    if output_dir is None:
        output_dir = Path("artifacts") / timestamp_now()
    ensure_dir(output_dir)

    if not is_admin():
        logger.warning("Not running as admin; some files or logs may be inaccessible.")

    max_bytes = max_dump_gb * 1024 * 1024 * 1024

    report = CopyReport(copied=[], skipped_large=[], missing=[])

    wer_dest = ensure_dir(output_dir / "wer")
    live_dest = ensure_dir(output_dir / "livekernelreports")
    mini_dest = ensure_dir(output_dir / "minidump")

    patterns = wer_patterns or WER_PATTERNS
    wer_dirs = find_latest_dirs(WER_QUEUE, patterns, latest_n)
    for d in wer_dirs:
        copy_dir_with_limit(
            d,
            wer_dest / d.name,
            report,
            max_bytes=max_bytes,
            include_large_dumps=include_large_dumps,
        )

    for sub in LIVE_KERNEL_FOLDERS:
        for f in find_latest_file_in_subdir(LIVE_KERNEL, sub, latest_n):
            dest = live_dest / sub / f.name
            copy_file_with_limit(
                f,
                dest,
                report,
                max_bytes=max_bytes,
                include_large_dumps=include_large_dumps,
            )

    for f in find_latest_files(MINIDUMP, latest_n):
        dest = mini_dest / f.name
        copy_file_with_limit(
            f,
            dest,
            report,
            max_bytes=max_bytes,
            include_large_dumps=include_large_dumps,
        )

    event_logs = export_event_logs(output_dir / "eventlogs", hours=hours)

    manifest = {
        "output_dir": str(output_dir),
        "latest_n": latest_n,
        "eventlog_hours": hours,
        "include_large_dumps": include_large_dumps,
        "max_dump_gb": max_dump_gb,
        "wer_patterns": patterns,
        "is_admin": is_admin(),
        "event_logs": event_logs,
        "copy_report": json.loads(report.to_json()),
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest
