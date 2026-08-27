from datetime import date, datetime

import pandas as pd
import pytest

from workpulse.view_cli import (
    WORK_CONTENT_COLUMNS,
    compute_work_summary,
    format_slot_line,
    format_summary_lines,
    load_slots,
    parse_target_date,
    run_interactive,
    update_confirmed_text,
)


def _seed(tmp_path, monkeypatch, target_date):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.parquet_io import append_row

    append_row(
        paths_module.work_content_path(target_date),
        {
            "slot_start": datetime(2026, 8, 26, 9, 0, 0),
            "slot_end": datetime(2026, 8, 26, 9, 30, 0),
            "predicted_text": "資料作成",
            "confirmed_text": "資料作成",
            "status": "auto_confirmed",
            "screenshot_path": "shot1.png",
        },
        WORK_CONTENT_COLUMNS,
    )
    return paths_module


def test_load_slots_returns_empty_when_no_file(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    df = load_slots(date(2026, 8, 26))
    assert len(df) == 0
    assert list(df.columns) == WORK_CONTENT_COLUMNS


def test_load_slots_returns_seeded_rows(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    df = load_slots(date(2026, 8, 26))
    assert len(df) == 1
    assert df.iloc[0]["confirmed_text"] == "資料作成"


def test_format_slot_line_includes_time_range_status_and_text():
    row = pd.Series(
        {
            "slot_start": datetime(2026, 8, 26, 9, 0, 0),
            "slot_end": datetime(2026, 8, 26, 9, 30, 0),
            "confirmed_text": "資料作成",
            "status": "auto_confirmed",
        }
    )
    line = format_slot_line(0, row)
    assert "09:00-09:30" in line
    assert "auto_confirmed" in line
    assert "資料作成" in line


def test_update_confirmed_text_updates_row_and_marks_confirmed(tmp_path, monkeypatch):
    paths_module = _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    update_confirmed_text(date(2026, 8, 26), 0, "会議対応")
    df = load_slots(date(2026, 8, 26))
    assert df.loc[0, "confirmed_text"] == "会議対応"
    assert df.loc[0, "status"] == "confirmed"


def test_update_confirmed_text_raises_for_invalid_index(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    with pytest.raises(IndexError):
        update_confirmed_text(date(2026, 8, 26), 5, "会議対応")


def test_run_interactive_reports_no_records_when_empty(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    outputs = []
    run_interactive(date(2026, 8, 27), input_func=lambda prompt: "", print_func=outputs.append)
    assert any("記録はありません" in line for line in outputs)


def test_run_interactive_edits_selected_slot(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    inputs = iter(["0", "会議対応", ""])
    outputs = []

    run_interactive(date(2026, 8, 26), input_func=lambda prompt: next(inputs), print_func=outputs.append)

    df = load_slots(date(2026, 8, 26))
    assert df.loc[0, "confirmed_text"] == "会議対応"
    assert any("保存しました" in line for line in outputs)


def test_parse_target_date():
    assert parse_target_date(["--date", "2026-08-26"]) == date(2026, 8, 26)


def test_compute_work_summary_aggregates_by_confirmed_text_desc():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 9, 0, 0),
                "slot_end": datetime(2026, 8, 26, 9, 30, 0),
                "confirmed_text": "資料作成",
                "status": "confirmed",
            },
            {
                "slot_start": datetime(2026, 8, 26, 9, 30, 0),
                "slot_end": datetime(2026, 8, 26, 10, 0, 0),
                "confirmed_text": "会議",
                "status": "confirmed",
            },
            {
                "slot_start": datetime(2026, 8, 26, 10, 0, 0),
                "slot_end": datetime(2026, 8, 26, 11, 0, 0),
                "confirmed_text": "資料作成",
                "status": "confirmed",
            },
            {
                "slot_start": datetime(2026, 8, 26, 11, 0, 0),
                "slot_end": datetime(2026, 8, 26, 11, 30, 0),
                "confirmed_text": "",
                "status": "confirmed",
            },
        ]
    )

    summary = compute_work_summary(df)

    assert summary[0][0] == "資料作成"
    assert summary[0][1] == pd.Timedelta(hours=1, minutes=30)
    assert summary[1][0] == "会議"
    assert summary[1][1] == pd.Timedelta(minutes=30)


def test_format_summary_lines_shows_hhmm_and_total():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 9, 0, 0),
                "slot_end": datetime(2026, 8, 26, 10, 30, 0),
                "confirmed_text": "資料作成",
                "status": "confirmed",
            },
        ]
    )

    lines = format_summary_lines(df)

    assert any("01:30" in line and "資料作成" in line for line in lines)
    assert any("合計" in line and "01:30" in line for line in lines)


def test_run_interactive_prints_summary_after_editing(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    outputs = []

    run_interactive(date(2026, 8, 26), input_func=lambda prompt: "", print_func=outputs.append)

    assert any("作業サマリー" in line for line in outputs)
    assert any("00:30" in line and "資料作成" in line for line in outputs)
