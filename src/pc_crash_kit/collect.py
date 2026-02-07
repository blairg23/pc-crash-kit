from __future__ import annotations

import glob
import json
import logging
import os
from pathlib import Path
from typing import Iterable

from .utils import (
    CopyReport,
    ensure_dir,
    is_admin,
    is_windows,
    load_config,
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


def find_latest_dirs(
    base: Path, patterns: list[str], latest_n: int, strict_access: bool = False
) -> list[Path]:
    try:
        if not base.exists():
            return []
    except OSError as exc:
        if strict_access:
            raise
        logger.warning("Unable to access %s: %s", base, exc)
        return []
    matches: list[Path] = []
    for pat in patterns:
        try:
            matches.extend([p for p in base.glob(pat) if p.is_dir()])
        except OSError as exc:
            if strict_access:
                raise
            logger.warning("Unable to glob %s in %s: %s", pat, base, exc)
    ordered = _sorted_by_mtime(matches)
    return ordered[-latest_n:]


def find_latest_files(
    base: Path, latest_n: int, strict_access: bool = False
) -> list[Path]:
    try:
        if not base.exists():
            return []
    except OSError as exc:
        if strict_access:
            raise
        logger.warning("Unable to access %s: %s", base, exc)
        return []
    try:
        files = [p for p in base.iterdir() if p.is_file()]
    except OSError as exc:
        if strict_access:
            raise
        logger.warning("Unable to list files in %s: %s", base, exc)
        return []
    ordered = _sorted_by_mtime(files)
    return ordered[-latest_n:]


def find_latest_file_in_subdir(
    base: Path, subdir: str, latest_n: int, strict_access: bool = False
) -> list[Path]:
    folder = base / subdir
    try:
        if not folder.exists():
            return []
    except OSError as exc:
        if strict_access:
            raise
        logger.warning("Unable to access %s: %s", folder, exc)
        return []
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError as exc:
        if strict_access:
            raise
        logger.warning("Unable to list files in %s: %s", folder, exc)
        return []
    ordered = _sorted_by_mtime(files)
    return ordered[-latest_n:] if ordered else []


def _normalize_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


def _expand_path(raw: str) -> Path:
    return Path(os.path.expandvars(raw)).expanduser()


def _safe_relpath(path: Path) -> Path:
    try:
        if path.is_absolute() and path.anchor:
            rel = path.relative_to(path.anchor)
            drive = path.drive.replace(":", "")
            return Path(drive) / rel if drive else rel
    except Exception:
        pass
    return path


def _copy_custom_paths(
    dest_root: Path,
    report: CopyReport,
    max_bytes: int,
    include_large_dumps: bool,
    files: list[str],
    dirs: list[str],
    globs: list[str],
) -> dict:
    custom_root = ensure_dir(dest_root)
    matched: list[str] = []

    for raw in files:
        src = _expand_path(raw)
        dest = custom_root / _safe_relpath(src)
        copy_file_with_limit(
            src, dest, report, max_bytes=max_bytes, include_large_dumps=include_large_dumps
        )

    for raw in dirs:
        src = _expand_path(raw)
        dest = custom_root / _safe_relpath(src)
        copy_dir_with_limit(
            src, dest, report, max_bytes=max_bytes, include_large_dumps=include_large_dumps
        )

    for pattern in globs:
        expanded = os.path.expandvars(pattern)
        for match in glob.glob(expanded, recursive=True):
            src = Path(match)
            if not src.is_file():
                continue
            matched.append(match)
            dest = custom_root / _safe_relpath(src)
            copy_file_with_limit(
                src, dest, report, max_bytes=max_bytes, include_large_dumps=include_large_dumps
            )

    return {"files": files, "dirs": dirs, "globs": globs, "glob_matches": matched}


def _copy_custom_groups(
    output_dir: Path,
    report: CopyReport,
    max_bytes: int,
    include_large_dumps: bool,
    groups: dict,
) -> dict:
    if not groups:
        return {}

    summary: dict[str, dict] = {}
    for name, spec in groups.items():
        if not isinstance(spec, dict):
            logger.warning("Custom group %s is not a table, skipping.", name)
            continue
        files = _normalize_list(spec.get("files"))
        dirs = _normalize_list(spec.get("dirs"))
        globs = _normalize_list(spec.get("globs"))
        dest_root = ensure_dir(output_dir / "custom" / str(name))
        summary[str(name)] = _copy_custom_paths(
            dest_root,
            report,
            max_bytes=max_bytes,
            include_large_dumps=include_large_dumps,
            files=files,
            dirs=dirs,
            globs=globs,
        )
    return summary


def export_event_logs(dest_dir: Path, hours: int) -> list[str]:
    ensure_dir(dest_dir)
    outputs: list[str] = []
    if not is_windows():
        logger.warning("Not running on Windows, skipping event log export.")
        return outputs

    script = Path(__file__).resolve().parents[2] / "scripts" / "export-eventlogs.ps1"
    cmd = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-OutputDir",
        str(dest_dir),
        "-Hours",
        str(hours),
    ]
    result = run_cmd(cmd, capture=True, check=False)
    if result.returncode != 0:
        logger.warning("Failed to export event logs: %s", result.stderr.strip())
        return outputs

    system_path = dest_dir / "System.evtx"
    app_path = dest_dir / "Application.evtx"
    if system_path.exists():
        outputs.append(str(system_path))
    if app_path.exists():
        outputs.append(str(app_path))
    return outputs


def collect(
    output_dir: Path | None,
    latest_n: int = DEFAULT_LATEST_N,
    hours: int = DEFAULT_EVENTLOG_HOURS,
    include_large_dumps: bool = False,
    max_dump_gb: int = DEFAULT_MAX_DUMP_GB,
    wer_patterns: list[str] | None = None,
    latest_livekernel: int | None = None,
    latest_minidump: int | None = None,
    require_admin: bool = False,
    strict_access: bool = False,
    config_path: Path | None = None,
) -> dict:
    if output_dir is None:
        output_dir = Path("artifacts") / timestamp_now()
    ensure_dir(output_dir)

    config, config_used = load_config(config_path)

    if require_admin and not is_admin():
        raise PermissionError("Admin privileges required. Re-run in an elevated shell.")

    if not is_admin():
        logger.warning("Not running as admin; some files or logs may be inaccessible.")

    max_bytes = max_dump_gb * 1024 * 1024 * 1024

    report = CopyReport(copied=[], skipped_large=[], missing=[])

    wer_dest = ensure_dir(output_dir / "wer")
    live_dest = ensure_dir(output_dir / "livekernelreports")
    mini_dest = ensure_dir(output_dir / "minidump")

    live_n = latest_livekernel if latest_livekernel is not None else latest_n
    mini_n = latest_minidump if latest_minidump is not None else latest_n

    strict = strict_access or require_admin

    cfg_paths = config.get("paths", {})
    wer_base = Path(cfg_paths.get("wer_queue", WER_QUEUE))
    live_base = Path(cfg_paths.get("livekernel_reports", LIVE_KERNEL))
    mini_base = Path(cfg_paths.get("minidump", MINIDUMP))

    cfg_wer = config.get("wer", {})
    patterns = wer_patterns or _normalize_list(cfg_wer.get("patterns")) or WER_PATTERNS
    wer_dirs = find_latest_dirs(wer_base, patterns, latest_n, strict_access=strict)
    for d in wer_dirs:
        copy_dir_with_limit(
            d,
            wer_dest / d.name,
            report,
            max_bytes=max_bytes,
            include_large_dumps=include_large_dumps,
        )

    cfg_live = config.get("livekernel", {})
    live_folders = _normalize_list(cfg_live.get("folders")) or LIVE_KERNEL_FOLDERS
    for sub in live_folders:
        for f in find_latest_file_in_subdir(
            live_base, sub, live_n, strict_access=strict
        ):
            dest = live_dest / sub / f.name
            copy_file_with_limit(
                f,
                dest,
                report,
                max_bytes=max_bytes,
                include_large_dumps=include_large_dumps,
            )

    for f in find_latest_files(mini_base, mini_n, strict_access=strict):
        dest = mini_dest / f.name
        copy_file_with_limit(
            f,
            dest,
            report,
            max_bytes=max_bytes,
            include_large_dumps=include_large_dumps,
        )

    cfg_custom = config.get("custom", {})
    if not isinstance(cfg_custom, dict):
        logger.warning("Config [custom] must be a table of groups.")
        cfg_custom = {}
    custom_report = _copy_custom_groups(
        output_dir,
        report,
        max_bytes=max_bytes,
        include_large_dumps=include_large_dumps,
        groups=cfg_custom,
    )

    event_logs = export_event_logs(output_dir / "eventlogs", hours=hours)

    manifest = {
        "output_dir": str(output_dir),
        "latest_n": latest_n,
        "latest_livekernel": live_n,
        "latest_minidump": mini_n,
        "eventlog_hours": hours,
        "include_large_dumps": include_large_dumps,
        "max_dump_gb": max_dump_gb,
        "wer_patterns": patterns,
        "livekernel_folders": live_folders,
        "paths": {
            "wer_queue": str(wer_base),
            "livekernel_reports": str(live_base),
            "minidump": str(mini_base),
        },
        "config_path": str(config_used) if config_used else None,
        "is_admin": is_admin(),
        "event_logs": event_logs,
        "custom": custom_report,
        "copy_report": json.loads(report.to_json()),
    }

    manifest_path = output_dir / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return manifest
