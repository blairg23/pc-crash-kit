from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

from .collect import collect
from .doctor import doctor
from .summarize import summarize


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)

    if args.command == "collect":
        manifest = collect(
            output_dir=args.output,
            latest_n=args.latest_n,
            hours=args.eventlog_hours,
            include_large_dumps=args.include_large_dumps,
            max_dump_gb=args.max_dump_gb,
            wer_patterns=args.wer_pattern,
        )
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
