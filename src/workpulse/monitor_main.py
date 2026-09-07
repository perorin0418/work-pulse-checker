from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from workpulse.activity import (
    ActiveWindowInfo,
    get_idle_seconds,
    read_active_window,
    win32_get_foreground_hwnd,
    win32_get_process_name_for_hwnd,
    win32_get_window_text,
)
from workpulse.parquet_io import append_row
from workpulse.paths import AUDIT_COLUMNS, audit_path


def collect_and_append(now: datetime, active: ActiveWindowInfo, idle_seconds: int) -> None:
    row = {
        "timestamp": now,
        "foreground_window_title": active.window_title,
        "foreground_process_name": active.process_name,
        "idle_seconds": idle_seconds,
    }
    append_row(audit_path(now.date()), row, AUDIT_COLUMNS)


def run() -> None:
    now = datetime.now()
    active = read_active_window(
        win32_get_foreground_hwnd, win32_get_window_text, win32_get_process_name_for_hwnd
    )
    idle_seconds = get_idle_seconds()
    collect_and_append(now, active, idle_seconds)


def main() -> None:
    try:
        run()
    except Exception:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "monitor_error.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        sys.exit(1)
