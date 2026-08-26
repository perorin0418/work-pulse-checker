from datetime import datetime

import pandas as pd

from workpulse.parquet_io import read_or_empty, append_row


def test_read_or_empty_returns_empty_frame_when_file_missing(tmp_path):
    columns = ["a", "b"]
    df = read_or_empty(tmp_path / "missing.parquet", columns)
    assert list(df.columns) == columns
    assert len(df) == 0


def test_append_row_creates_file_and_appends_rows(tmp_path):
    path = tmp_path / "audit.parquet"
    columns = ["timestamp", "foreground_window_title", "foreground_process_name", "idle_seconds"]

    append_row(
        path,
        {
            "timestamp": datetime(2026, 8, 26, 9, 0, 0),
            "foreground_window_title": "A",
            "foreground_process_name": "a.exe",
            "idle_seconds": 0,
        },
        columns,
    )
    append_row(
        path,
        {
            "timestamp": datetime(2026, 8, 26, 9, 1, 0),
            "foreground_window_title": "B",
            "foreground_process_name": "b.exe",
            "idle_seconds": 5,
        },
        columns,
    )

    df = pd.read_parquet(path)
    assert len(df) == 2
    assert list(df["foreground_window_title"]) == ["A", "B"]
    assert list(df["idle_seconds"]) == [0, 5]


def test_append_row_creates_parent_directory(tmp_path):
    path = tmp_path / "2026" / "08" / "26" / "audit.parquet"
    append_row(path, {"a": 1}, ["a"])
    assert path.exists()
