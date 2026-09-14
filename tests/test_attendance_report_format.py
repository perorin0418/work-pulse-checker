# tests/test_attendance_report_format.py
"""日報レコード（9項目）と ReportRow の変換のテスト。"""
from __future__ import annotations

import pytest

from workpulse.attendance.models import ReportRow
from workpulse.attendance.report_format import (
    NOTE_FIELDS,
    build_note,
    format_duration,
    parse_duration,
    parse_note,
    record_to_row,
    row_to_record,
    rows_from_records,
)

SAMPLE = {
    "業務種別": "直接原価",
    "ジョブコード": "2502044_【C25】標準準拠システム保守（共通機能）",
    "作業時間": "03:36",
    "詳細コード": "Z-02",
    "作業場所": "自宅（リモート）",
    "作業内容": "朝会",
    "状況": "完了",
    "保留・宿題事項": "なし",
    "課題・悩み": "なし",
}

EXPECTED_NOTE = (
    "【詳細コード】Z-02\n"
    "【作業場所】自宅（リモート）\n"
    "【作業内容】朝会\n"
    "【状況】完了\n"
    "【保留・宿題事項】なし\n"
    "【課題・悩み】なし"
)


def test_build_note_matches_specified_format():
    assert build_note(SAMPLE) == EXPECTED_NOTE


def test_build_note_fills_empty_with_placeholder():
    record = {**SAMPLE, "保留・宿題事項": "", "課題・悩み": ""}
    note = build_note(record)
    assert "【保留・宿題事項】なし" in note
    assert "【課題・悩み】なし" in note


def test_build_note_keeps_field_order():
    lines = build_note(SAMPLE).splitlines()
    assert [line[1 : line.index("】")] for line in lines] == NOTE_FIELDS


def test_record_to_row_maps_columns():
    row = record_to_row(SAMPLE)

    assert row.category == "直接原価"  # 業務列の上段
    assert row.service_name == "2502044_【C25】標準準拠システム保守（共通機能）"  # 下段
    assert row.plan_minutes is None  # 業務時間(予定) は入力しない
    assert row.result_minutes == 216  # 03:36
    assert row.note == EXPECTED_NOTE


def test_rows_from_records():
    rows = rows_from_records([SAMPLE, {**SAMPLE, "作業時間": "01:00", "作業内容": "実装"}])

    assert len(rows) == 2
    assert rows[1].result_minutes == 60
    assert "【作業内容】実装" in rows[1].note


def test_parse_note_round_trip():
    assert parse_note(EXPECTED_NOTE)["作業場所"] == "自宅（リモート）"
    assert parse_note(EXPECTED_NOTE)["詳細コード"] == "Z-02"


def test_parse_note_handles_multiline_value():
    note = "【作業内容】朝会\n続きの行\n【状況】完了"
    parsed = parse_note(note)
    assert parsed["作業内容"] == "朝会\n続きの行"
    assert parsed["状況"] == "完了"


def test_row_to_record_round_trip():
    record = row_to_record(record_to_row(SAMPLE))
    for field in ("業務種別", "ジョブコード", "作業時間", *NOTE_FIELDS):
        assert record[field] == SAMPLE[field]


def test_row_to_record_on_unformatted_note():
    record = row_to_record(ReportRow(category="直接原価", service_name="X", note="ただのメモ"))
    assert record["作業内容"] == ""
    assert record["業務種別"] == "直接原価"


@pytest.mark.parametrize(
    "text,expected",
    [("03:36", 216), ("01:00", 60), ("00:00", None), ("", None), ("あ", None)],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


@pytest.mark.parametrize(
    "minutes,expected", [(216, "03:36"), (60, "01:00"), (0, ""), (None, "")]
)
def test_format_duration(minutes, expected):
    assert format_duration(minutes) == expected


def test_status_stays_empty_when_blank():
    note = build_note({**SAMPLE, "状況": ""})
    assert "【状況】\n" in note + "\n"  # 「なし」で埋めない
    assert "【保留・宿題事項】なし" in note  # 他の項目は従来どおり補完


def test_status_value_is_kept_when_present():
    assert "【状況】完了" in build_note(SAMPLE)


def test_row_to_record_round_trip_with_empty_status():
    record = {**SAMPLE, "状況": ""}
    assert row_to_record(record_to_row(record))["状況"] == ""
