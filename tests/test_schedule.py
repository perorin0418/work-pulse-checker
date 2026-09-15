# tests/test_schedule.py
"""タスクスケジューラーの稼働時間帯の定義のテスト。"""
from __future__ import annotations

import pytest

from workpulse.schedule import (
    DEFAULT_REPETITION_DURATION,
    DEFAULT_START_BOUNDARY,
    active_hours,
    duration_hours,
    end_hour,
    start_hour,
)


def test_defaults_are_seven_to_twentytwo():
    assert active_hours() == (7, 22)


def test_start_hour_reads_boundary():
    assert start_hour("2026-01-01T07:00:00") == 7
    assert start_hour("2026-01-01T09:30:00") == 9


@pytest.mark.parametrize("duration,expected", [("PT15H", 15), ("PT1H", 1), ("PT8H30M", 8)])
def test_duration_hours(duration, expected):
    assert duration_hours(duration) == expected


def test_duration_hours_rejects_unparsable():
    with pytest.raises(ValueError):
        duration_hours("PT30M")  # 時間の指定が無い


def test_end_hour_is_clamped_to_24():
    assert end_hour("2026-01-01T20:00:00", "PT15H") == 24


def test_active_hours_follows_custom_schedule():
    assert active_hours("2026-01-01T09:00:00", "PT8H") == (9, 17)


def test_task_xml_uses_shared_duration():
    from workpulse.task_xml import build_task_xml

    xml = build_task_xml(
        command="uvw.exe",
        arguments='run --project "." python "monitor.py"',
        working_directory=".",
        start_boundary=DEFAULT_START_BOUNDARY,
        repetition_interval="PT1M",
    )
    assert f"<Duration>{DEFAULT_REPETITION_DURATION}</Duration>" in xml
    assert f"<StartBoundary>{DEFAULT_START_BOUNDARY}</StartBoundary>" in xml


def test_view_cli_blank_range_matches_schedule():
    from workpulse.view_cli import DEFAULT_BLANK_END_HOUR, DEFAULT_BLANK_START_HOUR

    assert (DEFAULT_BLANK_START_HOUR, DEFAULT_BLANK_END_HOUR) == active_hours()
