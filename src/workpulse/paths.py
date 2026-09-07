# src/workpulse/paths.py
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

DATA_ROOT = Path("data")

AUDIT_COLUMNS = ["timestamp", "foreground_window_title", "foreground_process_name", "idle_seconds"]

WORK_CONTENT_COLUMNS = [
    "slot_start",
    "slot_end",
    "predicted_text",
    "confirmed_text",
    "status",
    "screenshot_path",
]


def data_dir_for_date(d: date) -> Path:
    return DATA_ROOT / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"


def audit_path(d: date) -> Path:
    return data_dir_for_date(d) / "audit.parquet"


def work_content_path(d: date) -> Path:
    return data_dir_for_date(d) / "work-content.parquet"


def screenshot_dir(d: date) -> Path:
    return data_dir_for_date(d) / "screenshots"


def screenshot_path(dt: datetime) -> Path:
    return screenshot_dir(dt.date()) / f"{dt.strftime('%H%M')}.png"
