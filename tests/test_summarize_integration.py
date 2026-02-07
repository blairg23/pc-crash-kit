from __future__ import annotations

import json
from pathlib import Path

from pc_crash_kit.summarize import summarize


def _write_report(bundle_dir: Path) -> None:
    report_dir = bundle_dir / "wer" / "Kernel_193_test"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_text = "\n".join(
        [
            "EventType=LiveKernelEvent",
            "FriendlyEventName=Windows Hardware Error",
            "Sig[0].Name=Code",
            "Sig[0].Value=193",
            "Sig[1].Name=Parameter 1",
            "Sig[1].Value=80e",
            "DumpFile=C:\\Windows\\LiveKernelReports\\WATCHDOG\\WATCHDOG-123.dmp",
        ]
    )
    (report_dir / "Report.wer").write_text(report_text, encoding="utf-8")

    sysinfo_text = "\n".join(
        [
            "OS Name: Microsoft Windows 11 Pro",
            "System Manufacturer: ExampleCorp",
            "System Model: ExampleModel",
        ]
    )
    (report_dir / "sysinfo.txt").write_text(sysinfo_text, encoding="utf-8")

    memory_csv = "\n".join(
        [
            "Location,Total,Available",
            "Physical,16384,8192",
        ]
    )
    (report_dir / "memory.csv").write_text(memory_csv, encoding="utf-8")


def test_summarize_parses_wer_and_sysinfo(tmp_path: Path) -> None:
    _write_report(tmp_path)
    out_dir = tmp_path / "out"
    result = summarize(tmp_path, output_dir=out_dir)

    summary = json.loads(Path(result["summary_json"]).read_text(encoding="utf-8"))
    assert summary["report_count"] == 1
    assert summary["reports"][0]["event_type"] == "LiveKernelEvent"
    assert summary["reports"][0]["stop_code"] == "193"

    sysinfo = summary.get("sysinfo")
    assert sysinfo is not None
    assert sysinfo["data"]["OS Name"] == "Microsoft Windows 11 Pro"

    mem = summary.get("memory_csv")
    assert mem is not None
    assert mem["rows"][0]["Location"] == "Physical"
