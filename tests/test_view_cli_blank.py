# tests/test_view_cli_blank.py
"""記録が無い日を一から作成する挙動のテスト。"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from workpulse.paths import WORK_CONTENT_COLUMNS, work_content_path
from workpulse.view_cli import (
    DEFAULT_BLANK_END_HOUR,
    DEFAULT_BLANK_START_HOUR,
    generate_blank_slots,
    load_slots_for_edit,
    merge_blank_slots,
    run_interactive,
    update_confirmed_text,
)

DAY = date(2026, 9, 12)


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """データの保存先を一時ディレクトリに向ける。"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_existing(slots: list[tuple[int, int, str]]) -> None:
    """(時, 分, 内容) の一覧を work-content.parquet に保存する。"""
    rows = []
    for hour, minute, text in slots:
        start = pd.Timestamp(DAY) + pd.Timedelta(hours=hour, minutes=minute)
        rows.append(
            {
                "slot_start": start,
                "slot_end": start + pd.Timedelta(minutes=30),
                "predicted_text": text,
                "confirmed_text": text,
                "status": "confirmed",
                "screenshot_path": "",
            }
        )
    path = work_content_path(DAY)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=WORK_CONTENT_COLUMNS).to_parquet(path, index=False)


class Recorder:
    def __init__(self, answers: list[str]):
        self.answers = iter(answers)
        self.lines: list[str] = []

    def input(self, prompt=""):
        return next(self.answers)

    def print(self, text=""):
        self.lines.append(str(text))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def test_generate_blank_slots_covers_default_hours():
    blank = generate_blank_slots(DAY)

    expected = (DEFAULT_BLANK_END_HOUR - DEFAULT_BLANK_START_HOUR) * 2
    assert len(blank) == expected
    assert blank.iloc[0]["slot_start"] == pd.Timestamp("2026-09-12 09:00")
    assert blank.iloc[-1]["slot_end"] == pd.Timestamp("2026-09-12 18:00")
    assert set(blank["status"]) == {"missing"}
    assert set(blank["confirmed_text"]) == {""}


def test_generate_blank_slots_respects_custom_hours():
    blank = generate_blank_slots(DAY, start_hour=13, end_hour=15)
    assert len(blank) == 4
    assert blank.iloc[0]["slot_start"] == pd.Timestamp("2026-09-12 13:00")


def test_load_slots_for_edit_returns_blank_when_no_record(workdir):
    df = load_slots_for_edit(DAY)

    assert not df.empty
    assert set(df["status"]) == {"missing"}


def test_load_slots_for_edit_keeps_existing_by_default(workdir):
    write_existing([(9, 0, "朝会")])

    df = load_slots_for_edit(DAY)

    assert len(df) == 1  # 空枠で膨らませない
    assert df.iloc[0]["confirmed_text"] == "朝会"


def test_load_slots_for_edit_fills_blank_on_request(workdir):
    write_existing([(9, 0, "朝会")])

    df = load_slots_for_edit(DAY, fill_blank=True)

    assert len(df) == (DEFAULT_BLANK_END_HOUR - DEFAULT_BLANK_START_HOUR) * 2
    assert df.iloc[0]["confirmed_text"] == "朝会"  # 既存行は残る
    assert df.iloc[1]["status"] == "missing"


def test_merge_blank_slots_does_not_duplicate_existing(workdir):
    write_existing([(9, 0, "朝会"), (9, 30, "実装")])
    existing = pd.read_parquet(work_content_path(DAY))

    merged = merge_blank_slots(existing, DAY)

    starts = list(merged["slot_start"])
    assert len(starts) == len(set(starts))
    assert merged.iloc[0]["confirmed_text"] == "朝会"
    assert merged.iloc[1]["confirmed_text"] == "実装"


def test_update_creates_directory_when_missing(workdir):
    # 監視ログが無い日はディレクトリごと存在しない。
    assert not work_content_path(DAY).exists()

    update_confirmed_text(DAY, 0, "朝会", fill_blank=True)

    saved = pd.read_parquet(work_content_path(DAY))
    assert list(saved["confirmed_text"]) == ["朝会"]
    assert saved.iloc[0]["slot_start"] == pd.Timestamp("2026-09-12 09:00")


def test_interactive_creates_record_from_scratch(workdir):
    recorder = Recorder(["0", "朝会", "1", "設計作業", ""])

    run_interactive(DAY, input_func=recorder.input, print_func=recorder.print)

    saved = pd.read_parquet(work_content_path(DAY))
    assert list(saved["confirmed_text"]) == ["朝会", "設計作業"]
    assert list(saved["status"]) == ["confirmed", "confirmed"]
    assert "新規に作成します" in recorder.text


def test_interactive_keeps_slot_numbering_after_save(workdir):
    """1件保存しても一覧が縮まず、同じ番号で次の枠を編集できる。"""
    recorder = Recorder(["0", "朝会", "5", "午後の作業", ""])

    run_interactive(DAY, input_func=recorder.input, print_func=recorder.print)

    saved = pd.read_parquet(work_content_path(DAY)).sort_values("slot_start")
    assert list(saved["confirmed_text"]) == ["朝会", "午後の作業"]
    # 番号5は 11:30-12:00 の枠（9:00 から30分刻み）。
    assert saved.iloc[1]["slot_start"] == pd.Timestamp("2026-09-12 11:30")


def test_interactive_on_existing_day_is_unchanged(workdir):
    write_existing([(9, 0, "朝会")])
    recorder = Recorder([""])

    run_interactive(DAY, input_func=recorder.input, print_func=recorder.print)

    assert "新規に作成します" not in recorder.text
    assert "[0] 09:00-09:30 (confirmed) 朝会" in recorder.text
    assert "[1]" not in recorder.text  # 空枠で膨らませない
