# tests/test_work_history.py
from datetime import date, datetime

from workpulse.parquet_io import append_row
from workpulse.paths import WORK_CONTENT_COLUMNS, work_content_path
from workpulse.work_history import recent_confirmed_texts


def _append(target_date: date, slot_hour: int, confirmed_text: str) -> None:
    append_row(
        work_content_path(target_date),
        {
            "slot_start": datetime(target_date.year, target_date.month, target_date.day, slot_hour, 0, 0),
            "slot_end": datetime(target_date.year, target_date.month, target_date.day, slot_hour, 30, 0),
            "predicted_text": confirmed_text,
            "confirmed_text": confirmed_text,
            "status": "confirmed",
            "screenshot_path": "",
        },
        WORK_CONTENT_COLUMNS,
    )


def test_recent_confirmed_texts_returns_empty_list_when_no_file(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    assert recent_confirmed_texts(date(2026, 8, 27)) == []


def test_recent_confirmed_texts_returns_values_newest_first(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    _append(date(2026, 8, 27), 9, "資料作成")
    _append(date(2026, 8, 27), 10, "レビュー対応")

    result = recent_confirmed_texts(date(2026, 8, 27))
    assert result == ["レビュー対応", "資料作成"]


def test_recent_confirmed_texts_deduplicates_keeping_most_recent_order(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    _append(date(2026, 8, 27), 9, "資料作成")
    _append(date(2026, 8, 27), 10, "レビュー対応")
    _append(date(2026, 8, 27), 11, "資料作成")

    result = recent_confirmed_texts(date(2026, 8, 27))
    assert result == ["資料作成", "レビュー対応"]


def test_recent_confirmed_texts_skips_blank_entries(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    _append(date(2026, 8, 27), 9, "資料作成")
    _append(date(2026, 8, 27), 10, "")

    result = recent_confirmed_texts(date(2026, 8, 27))
    assert result == ["資料作成"]


def test_recent_confirmed_texts_respects_limit(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    for hour in range(9, 19):
        _append(date(2026, 8, 27), hour, f"作業{hour}")

    result = recent_confirmed_texts(date(2026, 8, 27), limit=3)
    assert result == ["作業18", "作業17", "作業16"]
