from datetime import date, datetime

import pandas as pd

from workpulse.activity import ActiveWindowInfo


def test_mark_finished_creates_marker(tmp_path, monkeypatch):
    from workpulse import paths as paths_module
    from workpulse.workday import is_finished, mark_finished

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    d = date(2026, 8, 26)
    assert not is_finished(d)
    mark_finished(d)
    assert is_finished(d)
    assert not is_finished(date(2026, 8, 27))


def test_monitor_run_skips_when_finished(tmp_path, monkeypatch):
    from workpulse import monitor_main
    from workpulse import paths as paths_module
    from workpulse.workday import mark_finished

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    mark_finished(date.today())
    called = []
    monkeypatch.setattr(monitor_main, "collect_and_append", lambda *a: called.append(a))
    monitor_main.run()
    assert called == []


def test_prompt_run_records_break_without_dialog(tmp_path, monkeypatch):
    from workpulse import paths as paths_module
    from workpulse import prompt_main

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 26, 12, 30, 0)

    monkeypatch.setattr(prompt_main, "datetime", FakeDatetime)
    monkeypatch.setattr(
        prompt_main, "run_confirm_dialog", lambda *a, **k: (_ for _ in ()).throw(AssertionError)
    )
    prompt_main.run()

    df = pd.read_parquet(paths_module.work_content_path(date(2026, 8, 26)))
    assert df.iloc[0]["confirmed_text"] == "休憩"
    assert df.iloc[0]["status"] == "break"


def test_prompt_run_skips_when_finished(tmp_path, monkeypatch):
    from workpulse import paths as paths_module
    from workpulse import prompt_main
    from workpulse.workday import mark_finished

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    mark_finished(date.today())
    monkeypatch.setattr(
        prompt_main, "try_save_screenshot", lambda *a: (_ for _ in ()).throw(AssertionError)
    )
    prompt_main.run()


def test_summary_excludes_break():
    from workpulse.view_cli import compute_work_summary

    df = pd.DataFrame(
        {
            "slot_start": [datetime(2026, 8, 26, 12, 0), datetime(2026, 8, 26, 13, 0)],
            "slot_end": [datetime(2026, 8, 26, 12, 30), datetime(2026, 8, 26, 13, 30)],
            "confirmed_text": ["休憩", "実装"],
        }
    )
    assert [t for t, _ in compute_work_summary(df)] == ["実装"]
