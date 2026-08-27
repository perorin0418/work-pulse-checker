# tests/test_paths.py
from datetime import date, datetime
from pathlib import Path

from workpulse.paths import (
    AUDIT_COLUMNS,
    WORK_CONTENT_COLUMNS,
    data_dir_for_date,
    audit_path,
    work_content_path,
    screenshot_dir,
    screenshot_path,
)


def test_data_dir_for_date_builds_year_month_day_path():
    assert data_dir_for_date(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26"


def test_audit_path():
    assert audit_path(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26" / "audit.parquet"


def test_work_content_path():
    assert work_content_path(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26" / "work-content.parquet"


def test_screenshot_dir():
    assert screenshot_dir(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26" / "screenshots"


def test_screenshot_path_formats_hhmm():
    dt = datetime(2026, 8, 26, 9, 30, 0)
    assert screenshot_path(dt) == Path("data") / "2026" / "08" / "26" / "screenshots" / "0930.png"


def test_audit_columns_schema():
    assert AUDIT_COLUMNS == [
        "timestamp",
        "foreground_window_title",
        "foreground_process_name",
        "idle_seconds",
    ]


def test_work_content_columns_schema():
    assert WORK_CONTENT_COLUMNS == [
        "slot_start",
        "slot_end",
        "predicted_text",
        "confirmed_text",
        "status",
        "screenshot_path",
    ]
