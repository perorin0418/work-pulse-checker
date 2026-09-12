from datetime import date, datetime

import json

import pandas as pd
import pytest

from workpulse.view_cli import (
    DAILY_REPORT_FIELDS,
    WORK_CONTENT_COLUMNS,
    build_daily_report_records,
    compute_work_summary,
    format_daily_report_json,
    format_slot_line,
    format_summary_lines,
    generate_missing_slots,
    load_slots,
    main,
    parse_args,
    parse_target_date,
    print_daily_report_json,
    print_summary,
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


def _seed_gap(tmp_path, monkeypatch, target_date):
    """10:00-10:30 と 11:30-12:00 に記録があり、10:30-11:30 が抜けている状態を作る。"""
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.parquet_io import append_row

    append_row(
        paths_module.work_content_path(target_date),
        {
            "slot_start": datetime(2026, 8, 26, 10, 0, 0),
            "slot_end": datetime(2026, 8, 26, 10, 30, 0),
            "predicted_text": "資料作成",
            "confirmed_text": "資料作成",
            "status": "confirmed",
            "screenshot_path": "shot1.png",
        },
        WORK_CONTENT_COLUMNS,
    )
    append_row(
        paths_module.work_content_path(target_date),
        {
            "slot_start": datetime(2026, 8, 26, 11, 30, 0),
            "slot_end": datetime(2026, 8, 26, 12, 0, 0),
            "predicted_text": "会議",
            "confirmed_text": "会議",
            "status": "confirmed",
            "screenshot_path": "shot2.png",
        },
        WORK_CONTENT_COLUMNS,
    )
    return paths_module


def test_generate_missing_slots_fills_gap_between_records():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 10, 0, 0),
                "slot_end": datetime(2026, 8, 26, 10, 30, 0),
                "predicted_text": "資料作成",
                "confirmed_text": "資料作成",
                "status": "confirmed",
                "screenshot_path": "shot1.png",
            },
            {
                "slot_start": datetime(2026, 8, 26, 11, 30, 0),
                "slot_end": datetime(2026, 8, 26, 12, 0, 0),
                "predicted_text": "会議",
                "confirmed_text": "会議",
                "status": "confirmed",
                "screenshot_path": "shot2.png",
            },
        ]
    )

    missing = generate_missing_slots(df)

    assert list(missing["slot_start"]) == [
        datetime(2026, 8, 26, 10, 30, 0),
        datetime(2026, 8, 26, 11, 0, 0),
    ]
    assert (missing["status"] == "missing").all()
    assert (missing["confirmed_text"] == "").all()


def test_generate_missing_slots_returns_empty_when_no_gap():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 10, 0, 0),
                "slot_end": datetime(2026, 8, 26, 10, 30, 0),
                "predicted_text": "資料作成",
                "confirmed_text": "資料作成",
                "status": "confirmed",
                "screenshot_path": "shot1.png",
            },
            {
                "slot_start": datetime(2026, 8, 26, 10, 30, 0),
                "slot_end": datetime(2026, 8, 26, 11, 0, 0),
                "predicted_text": "会議",
                "confirmed_text": "会議",
                "status": "confirmed",
                "screenshot_path": "shot2.png",
            },
        ]
    )

    missing = generate_missing_slots(df)

    assert missing.empty


def test_load_slots_includes_missing_slots_between_records(tmp_path, monkeypatch):
    _seed_gap(tmp_path, monkeypatch, date(2026, 8, 26))

    df = load_slots(date(2026, 8, 26))

    assert len(df) == 4
    assert list(df["status"]) == ["confirmed", "missing", "missing", "confirmed"]
    assert df.iloc[1]["slot_start"] == pd.Timestamp(2026, 8, 26, 10, 30, 0)
    assert df.iloc[2]["slot_start"] == pd.Timestamp(2026, 8, 26, 11, 0, 0)


def test_update_confirmed_text_can_fill_missing_slot(tmp_path, monkeypatch):
    _seed_gap(tmp_path, monkeypatch, date(2026, 8, 26))
    df = load_slots(date(2026, 8, 26))
    missing_index = df.index[df["status"] == "missing"][0]

    update_confirmed_text(date(2026, 8, 26), missing_index, "休憩")

    df = load_slots(date(2026, 8, 26))
    updated_row = df[df["slot_start"] == pd.Timestamp(2026, 8, 26, 10, 30, 0)].iloc[0]
    assert updated_row["confirmed_text"] == "休憩"
    assert updated_row["status"] == "confirmed"
    # 残り1件はまだmissingのまま
    assert (df["status"] == "missing").sum() == 1


def test_run_interactive_shows_and_edits_missing_slot(tmp_path, monkeypatch):
    _seed_gap(tmp_path, monkeypatch, date(2026, 8, 26))
    inputs = iter(["1", "休憩", ""])
    outputs = []

    run_interactive(date(2026, 8, 26), input_func=lambda prompt: next(inputs), print_func=outputs.append)

    assert any("missing" in line and "10:30-11:00" in line for line in outputs)
    df = load_slots(date(2026, 8, 26))
    updated_row = df[df["slot_start"] == pd.Timestamp(2026, 8, 26, 10, 30, 0)].iloc[0]
    assert updated_row["confirmed_text"] == "休憩"
    assert updated_row["status"] == "confirmed"


def test_parse_args_defaults_summary_to_false():
    args = parse_args(["--date", "2026-08-26"])
    assert args.date == "2026-08-26"
    assert args.summary is False


def test_parse_args_accepts_summary_flag():
    args = parse_args(["--date", "2026-08-26", "--summary"])
    assert args.summary is True


def test_print_summary_outputs_summary_lines_non_interactively(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    outputs = []

    print_summary(date(2026, 8, 26), print_func=outputs.append)

    assert any("作業サマリー" in line for line in outputs)
    assert any("00:30" in line and "資料作成" in line for line in outputs)
    assert any("合計" in line for line in outputs)


def test_print_summary_reports_no_records_when_file_missing(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    outputs = []

    print_summary(date(2026, 8, 27), print_func=outputs.append)

    assert any("記録はありません" in line for line in outputs)


def test_print_summary_reports_no_confirmed_work_when_all_unconfirmed(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    from workpulse.parquet_io import append_row

    target_date = date(2026, 8, 26)
    append_row(
        paths_module.work_content_path(target_date),
        {
            "slot_start": datetime(2026, 8, 26, 9, 0, 0),
            "slot_end": datetime(2026, 8, 26, 9, 30, 0),
            "predicted_text": "",
            "confirmed_text": "",
            "status": "missing",
            "screenshot_path": "",
        },
        WORK_CONTENT_COLUMNS,
    )
    outputs = []

    print_summary(target_date, print_func=outputs.append)

    assert any("確定済み作業内容はありません" in line for line in outputs)


def test_main_with_summary_flag_calls_print_summary_not_interactive(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))

    main(["--date", "2026-08-26", "--summary"])

    captured = capsys.readouterr()
    assert "作業サマリー" in captured.out


def test_daily_report_fields_match_expected_order():
    assert DAILY_REPORT_FIELDS == [
        "業務種別",
        "ジョブコード",
        "作業時間",
        "詳細コード",
        "作業場所",
        "作業内容",
        "状況",
        "保留・宿題事項",
        "課題・悩み",
    ]


def test_build_daily_report_records_maps_summary_to_report_fields():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 9, 0, 0),
                "slot_end": datetime(2026, 8, 26, 10, 30, 0),
                "confirmed_text": "資料作成",
                "status": "confirmed",
            },
            {
                "slot_start": datetime(2026, 8, 26, 10, 30, 0),
                "slot_end": datetime(2026, 8, 26, 11, 0, 0),
                "confirmed_text": "会議",
                "status": "confirmed",
            },
        ]
    )

    records = build_daily_report_records(df, classify_job_code_func=lambda text: "コードX")

    assert len(records) == 2
    assert records[0]["作業内容"] == "資料作成"
    assert records[0]["作業時間"] == "01:30"
    assert records[1]["作業内容"] == "会議"
    assert records[1]["作業時間"] == "00:30"
    for record in records:
        assert set(record.keys()) == set(DAILY_REPORT_FIELDS)
        assert record["業務種別"] == "直接原価"
        assert record["ジョブコード"] == "コードX"
        for field in DAILY_REPORT_FIELDS:
            if field not in ("業務種別", "ジョブコード", "作業内容", "作業時間"):
                assert record[field] == ""


def test_build_daily_report_records_passes_confirmed_text_to_classifier():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 9, 0, 0),
                "slot_end": datetime(2026, 8, 26, 9, 30, 0),
                "confirmed_text": "朝会",
                "status": "confirmed",
            },
        ]
    )
    captured = []

    def fake_classifier(text):
        captured.append(text)
        return "任意コード"

    records = build_daily_report_records(df, classify_job_code_func=fake_classifier)

    assert captured == ["朝会"]
    assert records[0]["ジョブコード"] == "任意コード"


def test_build_daily_report_records_returns_empty_list_when_no_confirmed_work():
    assert build_daily_report_records(pd.DataFrame()) == []


def test_format_daily_report_json_is_valid_json_matching_records():
    df = pd.DataFrame(
        [
            {
                "slot_start": datetime(2026, 8, 26, 9, 0, 0),
                "slot_end": datetime(2026, 8, 26, 9, 30, 0),
                "confirmed_text": "資料作成",
                "status": "confirmed",
            },
        ]
    )

    fake_classifier = lambda work_text: "コードY"
    fake_detail = lambda work_text, job_code: "Z-05"
    text = format_daily_report_json(
        df,
        classify_job_code_func=fake_classifier,
        classify_detail_code_func=fake_detail,
    )
    parsed = json.loads(text)

    assert parsed == build_daily_report_records(
        df,
        classify_job_code_func=fake_classifier,
        classify_detail_code_func=fake_detail,
    )


def test_print_daily_report_json_outputs_parseable_json_for_seeded_day(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    outputs = []

    print_daily_report_json(
        date(2026, 8, 26),
        print_func=outputs.append,
        classify_job_code_func=lambda work_text: "2502044_【C25】標準準拠システム保守（共通機能）",
        classify_detail_code_func=lambda work_text, job_code: "B-10",
    )

    assert len(outputs) == 1
    parsed = json.loads(outputs[0])
    assert parsed == [
        {
            "業務種別": "直接原価",
            "ジョブコード": "2502044_【C25】標準準拠システム保守（共通機能）",
            "作業時間": "00:30",
            "詳細コード": "B-10",
            "作業場所": "",
            "作業内容": "資料作成",
            "状況": "",
            "保留・宿題事項": "",
            "課題・悩み": "",
        }
    ]


def test_print_daily_report_json_outputs_empty_array_when_no_records(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    outputs = []

    print_daily_report_json(
        date(2026, 8, 27),
        print_func=outputs.append,
        classify_job_code_func=lambda work_text: "呼ばれないはず",
    )

    assert json.loads(outputs[0]) == []


def test_main_with_daily_report_json_flag_outputs_json(tmp_path, monkeypatch, capsys):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    monkeypatch.setattr(
        "workpulse.view_cli.classify_job_code",
        lambda work_text: "2502044_【C25】標準準拠システム保守（共通機能）",
    )

    main(["--date", "2026-08-26", "--daily-report-json"])

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed[0]["作業内容"] == "資料作成"
    assert parsed[0]["ジョブコード"] == "2502044_【C25】標準準拠システム保守（共通機能）"
