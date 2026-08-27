# src/workpulse/prompt_main.py
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from workpulse.audit_summary import summarize
from workpulse.confirm_ui import run_confirm_dialog
from workpulse.countdown_ui import run_countdown_window
from workpulse.haiku import predict_work_content
from workpulse.parquet_io import append_row, read_or_empty
from workpulse.paths import AUDIT_COLUMNS, audit_path, work_content_path
from workpulse.screenshot import capture_png_bytes_mss, try_save_screenshot

WORK_CONTENT_COLUMNS = [
    "slot_start",
    "slot_end",
    "predicted_text",
    "confirmed_text",
    "status",
    "screenshot_path",
]


def slot_bounds(now: datetime) -> tuple[datetime, datetime]:
    minute = 0 if now.minute < 30 else 30
    slot_start = now.replace(minute=minute, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=30)
    return slot_start, slot_end


def build_work_content_row(
    slot_start: datetime,
    slot_end: datetime,
    predicted_text: str,
    confirmed_text: str,
    status: str,
    screenshot_path: Path | None,
) -> dict:
    return {
        "slot_start": slot_start,
        "slot_end": slot_end,
        "predicted_text": predicted_text,
        "confirmed_text": confirmed_text,
        "status": status,
        "screenshot_path": str(screenshot_path) if screenshot_path is not None else "",
    }


def run() -> None:
    now = datetime.now()
    slot_start, slot_end = slot_bounds(now)

    run_countdown_window(30)

    shot_path = try_save_screenshot(now, capture_png_bytes_mss)

    audit_df = read_or_empty(audit_path(now.date()), AUDIT_COLUMNS)
    summary_text = summarize(audit_df, now)

    if shot_path is not None:
        predicted_text = predict_work_content(summary_text, shot_path)
    else:
        predicted_text = ""

    confirmed_text, status = run_confirm_dialog(predicted_text, timeout_seconds=300)

    row = build_work_content_row(slot_start, slot_end, predicted_text, confirmed_text, status, shot_path)
    append_row(work_content_path(now.date()), row, WORK_CONTENT_COLUMNS)


def main() -> None:
    try:
        run()
    except Exception:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "prompt_error.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        sys.exit(1)
