from datetime import datetime

import pandas as pd

from workpulse.audit_summary import recent_rows, summarize


def test_recent_rows_filters_by_window():
    df = pd.DataFrame({"timestamp": [datetime(2026, 8, 26, 9, 0, 0), datetime(2026, 8, 26, 8, 0, 0)]})
    result = recent_rows(df, datetime(2026, 8, 26, 9, 30, 0), window_minutes=30)
    assert len(result) == 1


def test_summarize_with_no_rows_reports_no_records():
    df = pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns]"),
            "foreground_window_title": pd.Series(dtype="object"),
            "foreground_process_name": pd.Series(dtype="object"),
            "idle_seconds": pd.Series(dtype="int64"),
        }
    )
    text = summarize(df, datetime(2026, 8, 26, 9, 30, 0))
    assert "操作記録なし" in text


def test_summarize_counts_top_titles_and_processes_within_window():
    df = pd.DataFrame(
        {
            "timestamp": [
                datetime(2026, 8, 26, 9, 10, 0),
                datetime(2026, 8, 26, 9, 20, 0),
                datetime(2026, 8, 26, 8, 0, 0),
            ],
            "foreground_window_title": ["Excel - 資料", "Excel - 資料", "Old App"],
            "foreground_process_name": ["excel.exe", "excel.exe", "old.exe"],
            "idle_seconds": [0, 0, 0],
        }
    )
    text = summarize(df, datetime(2026, 8, 26, 9, 30, 0), window_minutes=30)
    assert "Excel - 資料(2)" in text
    assert "excel.exe(2)" in text
    assert "Old App" not in text
