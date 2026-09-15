# src/workpulse/schedule.py
"""タスクスケジューラーの稼働時間帯の定義。

監視タスクが動く時間帯は「日報を手入力するときの枠の範囲」と同じであるべき
なので、開始時刻と稼働時間をここ1か所で持ち、タスク登録側
（`install_tasks_main`）と編集側（`view_cli`）の両方から参照する。
"""
from __future__ import annotations

import re

#: タスク登録時の開始日時。日付部分は「いつから有効か」を表すだけで、
#: 毎日の開始時刻は時刻部分（07:00）が決める。
DEFAULT_START_BOUNDARY = "2026-01-01T07:00:00"

#: 開始時刻から何時間繰り返すか（ISO 8601 duration）。07:00 + 15h = 22:00。
DEFAULT_REPETITION_DURATION = "PT15H"


def start_hour(start_boundary: str = DEFAULT_START_BOUNDARY) -> int:
    """稼働開始時刻（時）を返す。"""
    return int(start_boundary.split("T")[1].split(":")[0])


def duration_hours(duration: str = DEFAULT_REPETITION_DURATION) -> int:
    """ISO 8601 duration から時間数を取り出す。分は切り捨てる。"""
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
    if not match or not match.group(1):
        raise ValueError(f"時間を読み取れない duration: {duration!r}")
    return int(match.group(1))


def end_hour(
    start_boundary: str = DEFAULT_START_BOUNDARY,
    duration: str = DEFAULT_REPETITION_DURATION,
) -> int:
    """稼働終了時刻（時）を返す。24時を超える場合は24に丸める。"""
    return min(start_hour(start_boundary) + duration_hours(duration), 24)


def active_hours(
    start_boundary: str = DEFAULT_START_BOUNDARY,
    duration: str = DEFAULT_REPETITION_DURATION,
) -> tuple[int, int]:
    """稼働時間帯を (開始時, 終了時) で返す。既定は (7, 22)。"""
    return start_hour(start_boundary), end_hour(start_boundary, duration)
