from datetime import datetime

import pandas as pd

from workpulse.activity import ActiveWindowInfo


def test_collect_and_append_writes_expected_row(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.monitor_main import collect_and_append

    now = datetime(2026, 8, 26, 9, 31, 0)
    collect_and_append(now, ActiveWindowInfo(window_title="Notepad", process_name="notepad.exe"), 12)

    df = pd.read_parquet(paths_module.audit_path(now.date()))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["foreground_window_title"] == "Notepad"
    assert row["foreground_process_name"] == "notepad.exe"
    assert row["idle_seconds"] == 12


def test_collect_and_append_appends_second_row(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.monitor_main import collect_and_append

    now1 = datetime(2026, 8, 26, 9, 31, 0)
    now2 = datetime(2026, 8, 26, 9, 32, 0)
    collect_and_append(now1, ActiveWindowInfo(window_title="A", process_name="a.exe"), 0)
    collect_and_append(now2, ActiveWindowInfo(window_title="B", process_name="b.exe"), 3)

    df = pd.read_parquet(paths_module.audit_path(now1.date()))
    assert len(df) == 2
