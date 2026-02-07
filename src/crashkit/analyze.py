# src/crashkit/analyze.py
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Optional, Tuple

TIME_KEYS = ("TimeCreated", "TimeGenerated")
_FMT_SAMPLE = datetime(2000, 1, 1, 1, 1, 1, 123456)
_FMT_LEN_CACHE: dict[str, int] = {}

@dataclass
class Event:
    time: Optional[datetime]
    log: str
    event_id: Optional[int]
    level: str
    provider: str
    message: str

def _parse_dt(s: Any) -> Optional[datetime]:
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    if isinstance(s, str):
        text = s.strip()
        if not text:
            return None

        def _fmt_len(fmt: str) -> int:
            cached = _FMT_LEN_CACHE.get(fmt)
            if cached is None:
                cached = len(_FMT_SAMPLE.strftime(fmt))
                _FMT_LEN_CACHE[fmt] = cached
            return cached

        def _strip_tz(value: str) -> str:
            return re.sub(r"(Z|[+-]\d{2}:?\d{2})$", "", value)

        candidates = [text]
        stripped = _strip_tz(text)
        if stripped != text:
            candidates.append(stripped)

        formats = (
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%m/%d/%Y %I:%M:%S %p",
            "%Y-%m-%d %H:%M:%S",
        )

        # Handle typical Windows formats seen in exports
        for cand in candidates:
            for fmt in formats:
                try:
                    return datetime.strptime(cand, fmt)
                except Exception:
                    try:
                        expect_len = _fmt_len(fmt)
                        if len(cand) >= expect_len:
                            return datetime.strptime(cand[:expect_len], fmt)
                    except Exception:
                        pass

        # Try ISO-ish
        try:
            return datetime.fromisoformat(text.replace("Z", ""))
        except Exception:
            return None
    return None

def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            content = f.read().strip()
            if not content:
                return None
            return json.loads(content)
    except Exception:
        return None

def _ensure_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]

def _coerce_event(obj: dict, log: str) -> Event:
    t = None
    for k in TIME_KEYS:
        if k in obj:
            t = _parse_dt(obj.get(k))
            break
    eid = obj.get("Id")
    try:
        eid = int(eid) if eid is not None else None
    except Exception:
        eid = None

    level = str(obj.get("LevelDisplayName") or "").strip() or "?"
    provider = str(obj.get("ProviderName") or "").strip() or "?"
    msg = str(obj.get("Message") or "").strip()

    # Basic message cleanup
    msg = re.sub(r"\s+", " ", msg)
    return Event(time=t, log=log, event_id=eid, level=level, provider=provider, message=msg)

def load_events(bundle_dir: Path) -> List[Event]:
    logs_dir = bundle_dir / "logs"
    candidates = [
        ("System", logs_dir / "system_events.json"),
        ("Application", logs_dir / "application_events.json"),
        ("SystemProviderFocus", logs_dir / "system_provider_focus.json"),
        ("Reliability", logs_dir / "reliability_records.json"),
        ("WEROperational", logs_dir / "wer_systemerrorreporting.json"),
    ]

    events: List[Event] = []
    for log_name, p in candidates:
        raw = _load_json(p)
        for obj in _ensure_list(raw):
            if isinstance(obj, dict):
                events.append(_coerce_event(obj, log_name))
    # Sort by time (unknown times last)
    events.sort(key=lambda e: (e.time is None, e.time or datetime.min))
    return events

def score_suspects(events: List[Event]) -> List[Tuple[str, int]]:
    patterns = [
        ("GPU driver reset (TDR) or display stack", r"(Display driver|nvlddmkm|amdkmdag|DXGI|TDR|LiveKernelEvent|VIDEO_TDR|GPU)"),
        ("Kernel power / unexpected reboot", r"(Kernel-Power|Event ID 41|The system has rebooted without cleanly shutting down)"),
        ("Bugcheck / BSOD style crash", r"(bugcheck|MEMORY\.DMP|minidump|BlueScreen|STOP_CODE|0x[0-9A-Fa-f]+)"),
        ("WHEA hardware error (CPU, RAM, PCIe, GPU)", r"(WHEA|Machine Check Exception|Corrected hardware error)"),
        ("Game or app crash/hang", r"(Faulting application|AppHang|Exception code|stopped working|ARC Raiders|UE4|Unreal)"),
        ("Driver/service instability", r"(driver|service terminated|failed to start|DeviceSetupManager|Kernel-PnP)"),
        ("Disk/FS instability", r"(disk|ntfs|volmgr|storahci|Reset to device|bad block|corruption)"),
    ]

    counts = {name: 0 for name, _ in patterns}
    for e in events:
        blob = f"{e.provider} {e.message}"
        for name, pat in patterns:
            if re.search(pat, blob, re.IGNORECASE):
                counts[name] += 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [(k, v) for k, v in ranked if v > 0]

def extract_key_lines(events: List[Event], limit: int = 25) -> List[str]:
    # Focused high-signal IDs and providers
    high_ids = {41, 6008, 1001, 4101, 14, 13, 161, 219, 1000, 1002, 1026}
    high_provider = re.compile(r"(Kernel-Power|WHEA|nvlddmkm|Display|BugCheck|Windows Error Reporting|Application Error)", re.IGNORECASE)

    picks: List[Event] = []
    for e in events:
        if (e.event_id in high_ids) or high_provider.search(e.provider) or high_provider.search(e.message):
            picks.append(e)

    # Keep last N most relevant
    picks = picks[-limit:]
    lines = []
    for e in picks:
        t = e.time.isoformat(sep=" ", timespec="seconds") if e.time else "UNKNOWN_TIME"
        lines.append(f"[{t}] {e.log} ID={e.event_id} {e.provider}: {e.message}")
    return lines

def print_summary(bundle_dir: Path) -> int:
    events = load_events(bundle_dir)
    if not events:
        print("No events found. Make sure you pointed at the crash folder that contains logs/.")
        return 2

    suspects = score_suspects(events)
    key_lines = extract_key_lines(events)

    first_t = next((e.time for e in events if e.time), None)
    last_t = next((e.time for e in reversed(events) if e.time), None)

    print("CrashKit Summary")
    print(f"Bundle: {bundle_dir}")
    print(f"Events loaded: {len(events)}")
    print(f"Time range: {first_t} .. {last_t}")
    print("")

    if suspects:
        print("Top suspect buckets (count of matching signals):")
        for name, c in suspects[:6]:
            print(f"- {name}: {c}")
        print("")
    else:
        print("No strong suspect patterns detected from exported events.")
        print("")

    print("High-signal event lines:")
    for line in key_lines:
        print(f"- {line}")

    return 0

def main() -> int:
    ap = argparse.ArgumentParser(prog="crashkit", description="Analyze crash artifact bundles produced by collect-crash-artifacts.ps1")
    ap.add_argument("bundle_dir", help="Path to a crash-YYYYMMDD-HHMMSS folder (unzipped) or the extracted zip folder")
    args = ap.parse_args()

    bundle = Path(args.bundle_dir).resolve()
    if not bundle.exists():
        print(f"Path not found: {bundle}")
        return 2

    return print_summary(bundle)

if __name__ == "__main__":
    raise SystemExit(main())
