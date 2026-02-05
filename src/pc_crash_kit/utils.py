from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def is_admin() -> bool:
    if not is_windows():
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def timestamp_now() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_bytes(n: int) -> str:
    step = 1024.0
    size = float(n)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < step:
            return f"{size:.1f}{unit}"
        size /= step
    return f"{size:.1f}PB"


def run_cmd(cmd: Sequence[str], capture: bool = True, check: bool = False) -> subprocess.CompletedProcess:
    logger.debug("Running command: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=capture, text=True, check=check)


@dataclass
class CopyReport:
    copied: list[str]
    skipped_large: list[dict]
    missing: list[str]

    def to_json(self) -> str:
        return json.dumps(
            {
                "copied": self.copied,
                "skipped_large": self.skipped_large,
                "missing": self.missing,
            },
            indent=2,
        )


def _should_skip(path: Path, max_bytes: int, include_large_dumps: bool) -> bool:
    if include_large_dumps:
        return False
    try:
        return path.stat().st_size > max_bytes
    except OSError:
        return False


def copy_file_with_limit(
    src: Path,
    dest: Path,
    report: CopyReport,
    max_bytes: int,
    include_large_dumps: bool,
) -> None:
    try:
        if not src.exists():
            report.missing.append(str(src))
            return
    except OSError:
        report.missing.append(str(src))
        return

    if _should_skip(src, max_bytes, include_large_dumps):
        size_bytes = None
        try:
            size_bytes = src.stat().st_size
        except OSError:
            size_bytes = None
        report.skipped_large.append({"path": str(src), "size_bytes": size_bytes})
        return

    try:
        ensure_dir(dest.parent)
        shutil.copy2(src, dest)
        report.copied.append(str(dest))
    except OSError as exc:
        logger.warning("Failed to copy %s: %s", src, exc)
        report.missing.append(str(src))


def copy_dir_with_limit(
    src_dir: Path,
    dest_dir: Path,
    report: CopyReport,
    max_bytes: int,
    include_large_dumps: bool,
) -> None:
    try:
        if not src_dir.exists():
            report.missing.append(str(src_dir))
            return
    except OSError:
        report.missing.append(str(src_dir))
        return

    for root, dirs, files in os_walk(src_dir):
        rel = Path(root).relative_to(src_dir)
        target_root = dest_dir / rel
        ensure_dir(target_root)
        for name in files:
            src_file = Path(root) / name
            dest_file = target_root / name
            if _should_skip(src_file, max_bytes, include_large_dumps):
                size_bytes = None
                try:
                    size_bytes = src_file.stat().st_size
                except OSError:
                    size_bytes = None
                report.skipped_large.append({"path": str(src_file), "size_bytes": size_bytes})
                continue
            try:
                shutil.copy2(src_file, dest_file)
                report.copied.append(str(dest_file))
            except OSError as exc:
                logger.warning("Failed to copy %s: %s", src_file, exc)
                report.missing.append(str(src_file))


def os_walk(path: Path) -> Iterable[tuple[str, list[str], list[str]]]:
    return os.walk(path, onerror=lambda err: logger.warning("walk error: %s", err))
