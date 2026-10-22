# src/workpulse/workday.py
"""業務終了の目印。押した日だけ自動収集（monitor / prompt）を止める。"""
from __future__ import annotations

from datetime import date, datetime

from workpulse.paths import finished_marker_path


def is_finished(d: date) -> bool:
    return finished_marker_path(d).exists()


def mark_finished(d: date, now: datetime | None = None) -> None:
    path = finished_marker_path(d)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((now or datetime.now()).isoformat(), encoding="utf-8")


def main() -> None:
    today = date.today()
    if is_finished(today):
        print(f"{today.isoformat()} は既に業務終了済みです")
        return
    mark_finished(today)
    print(f"{today.isoformat()} の業務を終了しました。本日の自動収集を停止します")
