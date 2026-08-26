from datetime import datetime
from pathlib import Path

from workpulse.prompt_main import build_work_content_row, slot_bounds


def test_slot_bounds_for_first_half_of_hour():
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 5, 0))
    assert start == datetime(2026, 8, 26, 9, 0, 0)
    assert end == datetime(2026, 8, 26, 9, 30, 0)


def test_slot_bounds_for_second_half_of_hour():
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 47, 0))
    assert start == datetime(2026, 8, 26, 9, 30, 0)
    assert end == datetime(2026, 8, 26, 10, 0, 0)


def test_slot_bounds_crosses_hour_boundary():
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 58, 0))
    assert start == datetime(2026, 8, 26, 9, 30, 0)
    assert end == datetime(2026, 8, 26, 10, 0, 0)


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
