from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

from .collect import collect
from .doctor import doctor
from .summarize import summarize
from .utils import is_admin, is_wsl, wsl_to_windows_path, run_cmd


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pc-crash-kit",
        description="Collect and triage Windows crash artifacts.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    sub = parser.add_subparsers(dest="command", required=True)

    collect_p = sub.add_parser("collect", help="Collect crash artifacts into an output folder")
    collect_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: ./artifacts/<timestamp>/)",
    )
    collect_p.add_argument(
        "--latest-n",
        type=int,
        default=3,
        help="Number of newest items to collect from each source (default: 3)",
    )
    collect_p.add_argument(
        "--latest-livekernel",
        type=int,
        default=None,
        help="Number of newest LiveKernelReports files per subfolder (default: --latest-n)",
    )
    collect_p.add_argument(
        "--latest-minidump",
        type=int,
        default=None,
        help="Number of newest minidumps to collect (default: --latest-n)",
    )
    collect_p.add_argument(
        "--eventlog-hours",
        type=int,
        default=24,
        help="How many hours of System/Application logs to export (default: 24)",
    )
    collect_p.add_argument(
        "--include-large-dumps",
        action="store_true",
        help="Allow copy of dumps larger than the size limit",
    )
    collect_p.add_argument(
        "--max-dump-gb",
        type=int,
        default=1,
        help="Size limit for dump copies in GB (default: 1)",
    )
    collect_p.add_argument(
        "--require-admin",
        action="store_true",
        help="Exit if not running with admin privileges",
    )
    collect_p.add_argument(
        "--strict-access",
        action="store_true",
        help="Fail on access errors instead of skipping",
    )
    collect_p.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON summary to stdout",
    )
    collect_p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to pc-crash-kit.toml (default: auto-detect)",
    )
    collect_p.add_argument(
        "--wer-pattern",
        action="append",
        default=None,
        help=(
            "Glob pattern for WER ReportQueue directories. "
            "Repeat to add multiple patterns. "
            "Default: Kernel_193_*, Kernel_15e_*, Kernel_1a8_*"
        ),
    )

    summarize_p = sub.add_parser("summarize", help="Summarize a collected artifact bundle")
    summarize_p.add_argument("bundle_dir", type=Path, help="Path to an artifacts/<timestamp> folder")
    summarize_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for summary files (default: bundle_dir)",
    )

    doctor_p = sub.add_parser("doctor", help="Run non-destructive diagnostics and record output")
    doctor_p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output directory for doctor results (default: ./artifacts/doctor-<timestamp>/)",
    )
    doctor_p.add_argument(
        "--run-sfc",
        action="store_true",
        help="Run sfc /scannow (slow, requires admin)",
    )
    doctor_p.add_argument(
        "--dism-scan",
        action="store_true",
        help="Run DISM /ScanHealth (requires admin)",
    )
    doctor_p.add_argument(
        "--dism-restore",
        action="store_true",
        help="Run DISM /RestoreHealth (requires admin)",
    )

    return parser


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _convert_wsl_args(argv: Sequence[str]) -> list[str]:
    converted: list[str] = []
    path_opts = {"--output", "--config"}

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in path_opts and i + 1 < len(argv):
            converted.append(arg)
            converted.append(wsl_to_windows_path(Path(argv[i + 1]).expanduser()))
            i += 2
            continue
        if arg.startswith("--output="):
            value = arg.split("=", 1)[1]
            converted.append(f"--output={wsl_to_windows_path(Path(value).expanduser())}")
            i += 1
            continue
        converted.append(arg)
        i += 1

    if "summarize" in converted:
        idx = converted.index("summarize")
        for j in range(idx + 1, len(converted)):
            if converted[j].startswith("-"):
                continue
            converted[j] = wsl_to_windows_path(Path(converted[j]).expanduser())
            break

    return converted


def _with_admin_flags(argv: Sequence[str]) -> list[str]:
    updated = list(argv)
    if "--require-admin" not in updated:
        updated.append("--require-admin")
    if "--strict-access" not in updated:
        updated.append("--strict-access")
    return updated


def _windows_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _launch_elevated_windows(argv: Sequence[str]) -> int:
    repo_root = _windows_repo_root()
    win_repo = str(repo_root)
    win_src = f"{win_repo}\\src"
    win_args = _with_admin_flags(argv)
    win_args_str = " ".join(_ps_quote(arg) for arg in win_args)
    py_exe = sys.executable
    ps = (
        f"$env:PYTHONPATH={_ps_quote(win_src)}; "
        f"Set-Location -Path {_ps_quote(win_repo)}; "
        f"& {_ps_quote(py_exe)} -m pc_crash_kit.cli {win_args_str}"
    )
    start_cmd = (
        "Start-Process PowerShell -Verb RunAs "
        f"-WorkingDirectory {_ps_quote(win_repo)} "
        f"-ArgumentList '-NoExit','-Command',{_ps_quote(ps)}"
    )
    result = run_cmd(
        ["powershell.exe", "-NoProfile", "-Command", start_cmd],
        capture=False,
        check=False,
    )
    if result.returncode != 0:
        print("Failed to launch elevated PowerShell.", file=sys.stderr)
        return result.returncode
    print("Elevated run started in a new window.", file=sys.stderr)
    return 2


def _launch_elevated_from_wsl(argv: Sequence[str]) -> int:
    repo_root = _windows_repo_root()
    win_repo = wsl_to_windows_path(repo_root)
    win_src = f"{win_repo}\\src"
    win_args = _with_admin_flags(argv)
    win_args_str = " ".join(_ps_quote(arg) for arg in win_args)

    win_py = os.environ.get("PC_CRASH_KIT_WIN_PY")
    if win_py:
        py_cmd = f"& {_ps_quote(win_py)}"
    else:
        py_cmd = "py -3.12"

    ps = (
        f"$env:PYTHONPATH={_ps_quote(win_src)}; "
        f"Set-Location -Path {_ps_quote(win_repo)}; "
        f"{py_cmd} -m pc_crash_kit.cli {win_args_str}"
    )
    start_cmd = (
        "Start-Process PowerShell -Verb RunAs "
        f"-WorkingDirectory {_ps_quote(win_repo)} "
        f"-ArgumentList '-NoExit','-Command',{_ps_quote(ps)}"
    )
    result = run_cmd(
        ["powershell.exe", "-NoProfile", "-Command", start_cmd],
        capture=False,
        check=False,
    )
    if result.returncode != 0:
        print("Failed to launch elevated PowerShell from WSL.", file=sys.stderr)
        return result.returncode
    print("Elevated run started in a new window.", file=sys.stderr)
    return 2


def _delegate_to_windows(argv: Sequence[str]) -> int:
    repo_root = Path(__file__).resolve().parents[2]
    win_repo = wsl_to_windows_path(repo_root)
    win_src = f"{win_repo}\\src"

    win_args = _convert_wsl_args(argv)
    win_args_str = " ".join(_ps_quote(arg) for arg in win_args)

    win_py = os.environ.get("PC_CRASH_KIT_WIN_PY")
    if win_py:
        py_cmd = f"& {_ps_quote(win_py)}"
    else:
        py_cmd = "py -3.12"

    ps = (
        f"$env:PYTHONPATH={_ps_quote(win_src)}; "
        f"Set-Location -Path {_ps_quote(win_repo)}; "
        f"{py_cmd} -m pc_crash_kit.cli {win_args_str}; "
        "exit $LASTEXITCODE"
    )

    result = run_cmd(
        ["powershell.exe", "-NoProfile", "-Command", ps],
        capture=False,
        check=False,
    )
    if result.returncode == 127:
        print(
            "WSL detected but failed to launch Windows Python. "
            "Set PC_CRASH_KIT_WIN_PY to the full path of python.exe or install the py launcher.",
            file=sys.stderr,
        )
    return result.returncode


def _print_admin_instructions(argv: Sequence[str]) -> None:
    repo_root = _windows_repo_root()
    helper = str(repo_root / "scripts" / "pc-crash-kit.ps1")
    args = " ".join(_with_admin_flags(argv))

    print("Not running as admin. For full access, run one of the commands below:", file=sys.stderr)
    print("", file=sys.stderr)
    print("PowerShell (recommended):", file=sys.stderr)
    print(f"{helper} {args}", file=sys.stderr)

    print("", file=sys.stderr)
    print("Run this in PS:", file=sys.stderr)
    print("$repo = (Get-Location).Path", file=sys.stderr)
    print("$env:PYTHONPATH = \"$repo\\src\"", file=sys.stderr)
    print(f"python -m pc_crash_kit.cli {args}", file=sys.stderr)

    if is_wsl():
        win_repo = wsl_to_windows_path(repo_root)
        win_cmd = (
            "powershell.exe -NoProfile -Command "
            "\"Start-Process PowerShell -Verb RunAs -ArgumentList '-NoExit','-Command',"
            f"\\\"cd {win_repo}; $env:PYTHONPATH='{win_repo}\\\\src'; python -m pc_crash_kit.cli {args}\\\"\""
        )
        print("", file=sys.stderr)
        print("WSL (opens UAC prompt):", file=sys.stderr)
        print(win_cmd, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = list(sys.argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if is_wsl():
        if args.command == "collect" and (args.require_admin or args.strict_access):
            return _launch_elevated_from_wsl(argv)
        return _delegate_to_windows(argv)

    if args.command == "collect" and (args.require_admin or args.strict_access) and not is_admin():
        return _launch_elevated_windows(argv)

    if args.command == "collect" and not is_admin():
        _print_admin_instructions(argv)

    if args.command == "collect":
        try:
            manifest = collect(
                output_dir=args.output,
                latest_n=args.latest_n,
                hours=args.eventlog_hours,
                include_large_dumps=args.include_large_dumps,
                max_dump_gb=args.max_dump_gb,
                wer_patterns=args.wer_pattern,
                latest_livekernel=args.latest_livekernel,
                latest_minidump=args.latest_minidump,
                require_admin=args.require_admin,
                strict_access=args.strict_access,
                config_path=args.config,
            )
        except PermissionError as exc:
            print(str(exc), file=sys.stderr)
            _print_admin_instructions(argv)
            return 2
        if args.json:
            payload = {
                "output_dir": manifest["output_dir"],
                "manifest_path": manifest.get("manifest_path"),
                "copied": len(manifest["copy_report"]["copied"]),
                "skipped_large": len(manifest["copy_report"]["skipped_large"]),
                "missing": len(manifest["copy_report"]["missing"]),
            }
            print(json.dumps(payload))
        else:
            print("Collection complete")
            print(f"Output: {manifest['output_dir']}")
            print(f"Copied: {len(manifest['copy_report']['copied'])}")
            print(f"Skipped large: {len(manifest['copy_report']['skipped_large'])}")
            print(f"Missing: {len(manifest['copy_report']['missing'])}")
        return 0

    if args.command == "summarize":
        summary = summarize(args.bundle_dir, output_dir=args.output)
        print("Summary written")
        print(f"JSON: {summary['summary_json']}")
        print(f"Text: {summary['summary_txt']}")
        return 0

    if args.command == "doctor":
        result = doctor(
            output_dir=args.output,
            run_sfc=args.run_sfc,
            dism_scan=args.dism_scan,
            dism_restore=args.dism_restore,
        )
        print("Doctor results written")
        print(f"Output: {result['output_dir']}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
