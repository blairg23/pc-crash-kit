from __future__ import annotations

import csv
import json
import logging
import platform
import re
from pathlib import Path
from typing import Any

from .utils import ensure_dir, format_bytes, is_windows, run_cmd, timestamp_now

logger = logging.getLogger(__name__)


def _read_text_guess(path: Path) -> str:
    for enc in ("utf-16", "utf-8-sig", "utf-8", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return ""


def _parse_wmic_list(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            if current:
                items.append(current)
                current = {}
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            current[k.strip()] = v.strip()
    if current:
        items.append(current)
    return items


def _wmic(query: list[str]) -> list[dict[str, str]]:
    if not is_windows():
        return []
    result = run_cmd(["wmic", *query, "/format:list"], capture=True, check=False)
    if result.returncode != 0:
        logger.warning("WMIC failed: %s", result.stderr.strip())
        return []
    return _parse_wmic_list(result.stdout)


def get_gpu_info() -> list[dict[str, str]]:
    return _wmic(["path", "Win32_VideoController", "get", "Name,DriverVersion,DriverDate"])


def get_os_info() -> dict[str, str]:
    if not is_windows():
        return {
            "platform": platform.platform(),
            "release": platform.release(),
            "version": platform.version(),
        }
    items = _wmic(["os", "get", "Caption,Version,BuildNumber"])
    return items[0] if items else {}


def _find_latest_named_file(base: Path, filename: str) -> Path | None:
    matches = [
        p for p in base.rglob("*") if p.is_file() and p.name.lower() == filename.lower()
    ]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _parse_sysinfo_text(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in text.splitlines():
        if not line.strip():
            continue
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if key in data:
                existing = data[key]
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    data[key] = [existing, value]
            else:
                data[key] = value
            current_key = key
        elif current_key:
            extra = line.strip()
            if not extra:
                continue
            existing = data.get(current_key, "")
            if isinstance(existing, list):
                existing[-1] = f"{existing[-1]} {extra}".strip()
            else:
                data[current_key] = f"{existing} {extra}".strip()
    return data


def _load_sysinfo(bundle_dir: Path) -> dict[str, Any] | None:
    path = _find_latest_named_file(bundle_dir, "sysinfo.txt")
    if not path:
        return None
    text = _read_text_guess(path)
    if not text:
        return None
    return {"path": str(path), "data": _parse_sysinfo_text(text)}


def _load_memory_csv(bundle_dir: Path) -> dict[str, Any] | None:
    path = _find_latest_named_file(bundle_dir, "memory.csv")
    if not path:
        return None
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = [row for row in reader]
        return {"path": str(path), "rows": rows}
    except Exception:
        return None


def parse_wer_report(path: Path) -> dict[str, Any]:
    raw = _read_text_guess(path)
    data: dict[str, str] = {}
    sig_values: dict[str, str] = {}
    sig_names: dict[str, str] = {}
    ns_values: dict[str, str] = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        data[key] = value

        m = re.match(r"Sig\[(\d+)\]\.Value", key)
        if m:
            sig_values[m.group(1)] = value
            continue
        m = re.match(r"Sig\[(\d+)\]\.Name", key)
        if m:
            sig_names[m.group(1)] = value
            continue
        m = re.match(r"Ns\[(\d+)\]\.Value", key)
        if m:
            ns_values[m.group(1)] = value

    stop_code = None
    for key in ("StopCode", "Stopcode", "Code", "BugcheckCode", "Bugcheck"):
        if key in data:
            stop_code = data[key]
            break

    if stop_code is None:
        for idx, name in sig_names.items():
            if name.lower() in {"stopcode", "code", "bugcheck", "bugcheckcode"}:
                stop_code = sig_values.get(idx)
                break

    if stop_code is None and "0" in sig_values:
        stop_code = sig_values.get("0")

    report = {
        "path": str(path),
        "event_type": data.get("EventType"),
        "friendly_event_name": data.get("FriendlyEventName"),
        "sig_values": sig_values,
        "sig_names": sig_names,
        "ns_values": ns_values,
        "stop_code": stop_code,
        "dump_file": data.get("DumpFile") or data.get("DumpPath"),
        "report_id": data.get("ReportIdentifier"),
        "problem_signature": data.get("ProblemSignature") or data.get("ProblemSignatures"),
    }
    return report


def _signature_key(report: dict[str, Any]) -> str:
    sig0 = report.get("sig_values", {}).get("0")
    sig1 = report.get("sig_values", {}).get("1")
    if sig0 or sig1:
        return f"Sig0={sig0 or 'NA'} Sig1={sig1 or 'NA'}"
    if report.get("event_type"):
        return f"EventType={report['event_type']}"
    return "Unknown"


def _collect_artifact_stats(bundle_dir: Path) -> dict[str, Any]:
    stats: dict[str, Any] = {}

    wer_dir = bundle_dir / "wer"
    reports = list(wer_dir.rglob("Report.wer")) if wer_dir.exists() else []

    live_dir = bundle_dir / "livekernelreports"
    live_files = list(live_dir.rglob("*")) if live_dir.exists() else []
    live_files = [p for p in live_files if p.is_file()]

    mini_dir = bundle_dir / "minidump"
    mini_files = list(mini_dir.glob("*.dmp")) if mini_dir.exists() else []

    stats["wer_report_count"] = len(reports)
    stats["livekernel_files"] = len(live_files)
    stats["minidump_files"] = len(mini_files)

    if live_files:
        largest = max(live_files, key=lambda p: p.stat().st_size)
        stats["largest_livekernel_file"] = {
            "path": str(largest),
            "size": format_bytes(largest.stat().st_size),
        }

    if mini_files:
        largest = max(mini_files, key=lambda p: p.stat().st_size)
        stats["largest_minidump_file"] = {
            "path": str(largest),
            "size": format_bytes(largest.stat().st_size),
        }

    return stats


def summarize(bundle_dir: Path, output_dir: Path | None = None) -> dict[str, str]:
    bundle_dir = bundle_dir.resolve()
    if not bundle_dir.exists():
        raise FileNotFoundError(f"Bundle directory not found: {bundle_dir}")
    if not bundle_dir.is_dir():
        raise NotADirectoryError(f"Bundle path is not a directory: {bundle_dir}")
    if output_dir is None:
        output_dir = bundle_dir
    ensure_dir(output_dir)

    wer_dir = bundle_dir / "wer"
    report_paths = list(wer_dir.rglob("Report.wer")) if wer_dir.exists() else []
    reports = [parse_wer_report(p) for p in report_paths]

    signature_counts: dict[str, int] = {}
    for report in reports:
        key = _signature_key(report)
        signature_counts[key] = signature_counts.get(key, 0) + 1

    signature_list = sorted(
        [{"signature": k, "count": v} for k, v in signature_counts.items()],
        key=lambda item: item["count"],
        reverse=True,
    )

    manifest_path = bundle_dir / "manifest.json"
    manifest = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = None

    summary = {
        "generated_at": timestamp_now(),
        "bundle_dir": str(bundle_dir),
        "artifact_stats": _collect_artifact_stats(bundle_dir),
        "report_count": len(reports),
        "signature_counts": signature_list,
        "reports": reports,
        "gpu": get_gpu_info(),
        "os": get_os_info(),
        "sysinfo": _load_sysinfo(bundle_dir),
        "memory_csv": _load_memory_csv(bundle_dir),
        "manifest": manifest,
    }

    summary_json_path = output_dir / "summary.json"
    summary_txt_path = output_dir / "summary.txt"

    summary_json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = []
    lines.append("pc-crash-kit summary")
    lines.append(f"Bundle: {bundle_dir}")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append(f"WER reports: {summary['report_count']}")

    stats = summary.get("artifact_stats", {})
    lines.append(f"LiveKernelReports files: {stats.get('livekernel_files', 0)}")
    lines.append(f"Minidump files: {stats.get('minidump_files', 0)}")

    if signature_list:
        lines.append("")
        lines.append("Top signatures:")
        for item in signature_list[:10]:
            lines.append(f"- {item['signature']} ({item['count']})")

    if summary["gpu"]:
        lines.append("")
        lines.append("GPU:")
        for gpu in summary["gpu"]:
            name = gpu.get("Name", "Unknown")
            ver = gpu.get("DriverVersion", "Unknown")
            date = gpu.get("DriverDate", "Unknown")
            lines.append(f"- {name} DriverVersion={ver} DriverDate={date}")

    if summary["os"]:
        lines.append("")
        lines.append("OS:")
        for k, v in summary["os"].items():
            lines.append(f"- {k}: {v}")

    if summary.get("sysinfo"):
        info = summary["sysinfo"]["data"]
        lines.append("")
        lines.append("Sysinfo:")
        for key in ("OS Name", "System Manufacturer", "System Model", "System Type"):
            if key in info:
                lines.append(f"- {key}: {info[key]}")

    if summary.get("memory_csv"):
        rows = summary["memory_csv"].get("rows", [])
        lines.append("")
        lines.append(f"Memory CSV rows: {len(rows)}")

    summary_txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "summary_json": str(summary_json_path),
        "summary_txt": str(summary_txt_path),
    }
