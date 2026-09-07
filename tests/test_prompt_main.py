from datetime import datetime
from pathlib import Path

from workpulse.prompt_main import build_work_content_row, slot_bounds


def test_slot_bounds_at_top_of_hour_returns_previous_half_hour():
    # ちょうど9:00起動 -> 直前に終わった枠は8:30〜9:00
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 0, 0))
    assert start == datetime(2026, 8, 26, 8, 30, 0)
    assert end == datetime(2026, 8, 26, 9, 0, 0)


def test_slot_bounds_at_half_past_returns_first_half_hour():
    # ちょうど9:30起動 -> 直前に終わった枠は9:00〜9:30
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 30, 0))
    assert start == datetime(2026, 8, 26, 9, 0, 0)
    assert end == datetime(2026, 8, 26, 9, 30, 0)


def test_slot_bounds_crosses_hour_boundary():
    # ちょうど10:00起動 -> 直前に終わった枠は9:30〜10:00（時をまたぐ）
    start, end = slot_bounds(datetime(2026, 8, 26, 10, 0, 0))
    assert start == datetime(2026, 8, 26, 9, 30, 0)
    assert end == datetime(2026, 8, 26, 10, 0, 0)


def test_slot_bounds_tolerates_slightly_late_trigger():
    # タスク起動が数秒遅れても同じ枠になる
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 30, 15))
    assert start == datetime(2026, 8, 26, 9, 0, 0)
    assert end == datetime(2026, 8, 26, 9, 30, 0)


def test_build_work_content_row_returns_expected_fields():
    row = build_work_content_row(
        datetime(2026, 8, 26, 9, 0, 0),
        datetime(2026, 8, 26, 9, 30, 0),
        "predicted",
        "confirmed",
        "confirmed",
        Path("shot.png"),
    )
    assert row == {
        "slot_start": datetime(2026, 8, 26, 9, 0, 0),
        "slot_end": datetime(2026, 8, 26, 9, 30, 0),
        "predicted_text": "predicted",
        "confirmed_text": "confirmed",
        "status": "confirmed",
        "screenshot_path": "shot.png",
    }


def test_build_work_content_row_handles_missing_screenshot():
    row = build_work_content_row(
        datetime(2026, 8, 26, 9, 0, 0),
        datetime(2026, 8, 26, 9, 30, 0),
        "predicted",
        "confirmed",
        "confirmed",
        None,
    )
    assert row["screenshot_path"] == ""
