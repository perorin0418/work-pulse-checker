# tests/test_attendance_cli.py
"""日報登録 CLI のテスト。勤怠サービスには接続しない。"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date

import pytest

from workpulse.attendance.cli import (
    days_between,
    format_preview,
    parse_date_range,
    previous_workday,
    resolve_date,
    resolve_range,
    run,
)

RECORD = {
    "業務種別": "直接原価",
    "ジョブコード": "2502044",
    "作業時間": "03:36",
    "詳細コード": "Z-02",
    "作業場所": "自宅（リモート）",
    "作業内容": "朝会",
    "状況": "",
    "保留・宿題事項": "なし",
    "課題・悩み": "なし",
}


class FakeProvider:
    def __init__(self):
        self.submitted = []
        self.replace_flags = []
        self.closed = False

    def submit_report(self, report, replace: bool = True):
        self.submitted.append(report)
        self.replace_flags.append(replace)
        from workpulse.attendance.models import SubmitResult

        return SubmitResult(work_date=report.work_date, changed=True)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_open():
    provider = FakeProvider()

    @contextmanager
    def opener():
        try:
            yield provider
        finally:
            provider.close()

    opener.provider = provider
    return opener


@pytest.fixture
def json_file(tmp_path):
    def make(records):
        path = tmp_path / "records.json"
        path.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
        return str(path)

    return make


class Printer:
    def __init__(self):
        self.lines: list[str] = []

    def __call__(self, text=""):
        self.lines.append(str(text))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def test_previous_workday_skips_weekend():
    assert previous_workday(date(2026, 9, 14)) == date(2026, 9, 11)  # 月曜 -> 金曜
    assert previous_workday(date(2026, 9, 11)) == date(2026, 9, 10)  # 金曜 -> 木曜


def test_resolve_date_uses_argument():
    assert resolve_date("2026-09-11") == date(2026, 9, 11)


def test_resolve_date_defaults_to_previous_workday():
    got = resolve_date(None, input_func=lambda _: "", today=date(2026, 9, 14))
    assert got == date(2026, 9, 11)


def test_resolve_range_uses_argument():
    assert resolve_range("2026-09-11") == (date(2026, 9, 11), date(2026, 9, 11))


def test_resolve_range_prompts_when_missing():
    got = resolve_range(None, input_func=lambda _: "2026-09-11")
    assert got == (date(2026, 9, 11), date(2026, 9, 11))


def test_resolve_range_defaults_to_previous_workday():
    got = resolve_range(None, input_func=lambda _: "", today=date(2026, 9, 14))
    assert got == (date(2026, 9, 11), date(2026, 9, 11))


def test_resolve_range_prompt_accepts_range():
    got = resolve_range(None, input_func=lambda _: "2026-09-07~2026-09-11")
    assert got == (date(2026, 9, 7), date(2026, 9, 11))


@pytest.mark.parametrize("sep", ["~", "～", "〜", " ~ "])
def test_parse_date_range_separators(sep):
    assert parse_date_range(f"2026-09-07{sep}2026-09-11") == (date(2026, 9, 7), date(2026, 9, 11))


def test_parse_date_range_rejects_reversed():
    with pytest.raises(ValueError):
        parse_date_range("2026-09-11~2026-09-07")


def test_days_between_includes_both_ends():
    assert days_between(date(2026, 9, 10), date(2026, 9, 12)) == [
        date(2026, 9, 10),
        date(2026, 9, 11),
        date(2026, 9, 12),
    ]


def test_format_preview_lists_all_fields():
    text = format_preview(date(2026, 9, 11), [RECORD])
    for field in RECORD:
        assert field in text
    assert "2026-09-11" in text


def test_run_submits_with_yes(fake_open, json_file):
    printer = Printer()
    code = run(
        ["--date", "2026-09-11", "--json", json_file([RECORD]), "--yes"],
        print_func=printer,
        open_provider_func=fake_open,
    )

    assert code == 0
    provider = fake_open.provider
    assert len(provider.submitted) == 1
    report = provider.submitted[0]
    assert report.work_date == date(2026, 9, 11)
    assert report.rows[0].category == "直接原価"
    assert report.rows[0].service_name == "2502044"
    assert report.rows[0].result_minutes == 216
    assert provider.closed is True
    assert "登録しました" in printer.text


def test_run_dry_run_does_not_submit(fake_open, json_file):
    printer = Printer()
    code = run(
        ["--date", "2026-09-11", "--json", json_file([RECORD]), "--dry-run"],
        print_func=printer,
        open_provider_func=fake_open,
    )

    assert code == 0
    assert fake_open.provider.submitted == []
    assert "登録しません" in printer.text


def test_run_asks_for_confirmation(fake_open, json_file):
    printer = Printer()
    code = run(
        ["--date", "2026-09-11", "--json", json_file([RECORD])],
        print_func=printer,
        input_func=lambda _: "n",
        open_provider_func=fake_open,
    )

    assert code == 1
    assert fake_open.provider.submitted == []
    assert "中止しました" in printer.text


def test_run_accepts_yes_answer(fake_open, json_file):
    code = run(
        ["--date", "2026-09-11", "--json", json_file([RECORD])],
        print_func=Printer(),
        input_func=lambda _: "y",
        open_provider_func=fake_open,
    )

    assert code == 0
    assert len(fake_open.provider.submitted) == 1


def test_run_append_flag(fake_open, json_file):
    run(
        ["--date", "2026-09-11", "--json", json_file([RECORD]), "--yes", "--append"],
        print_func=Printer(),
        open_provider_func=fake_open,
    )

    assert fake_open.provider.replace_flags == [False]


def test_run_replaces_by_default(fake_open, json_file):
    run(
        ["--date", "2026-09-11", "--json", json_file([RECORD]), "--yes"],
        print_func=Printer(),
        open_provider_func=fake_open,
    )

    assert fake_open.provider.replace_flags == [True]


def test_run_rejects_bad_date(fake_open):
    printer = Printer()
    code = run(["--date", "2026/09/11"], print_func=printer, open_provider_func=fake_open)

    assert code == 2
    assert "形式" in printer.text


def test_run_reports_empty_records(fake_open, json_file):
    printer = Printer()
    code = run(
        ["--date", "2026-09-11", "--json", json_file([]), "--yes"],
        print_func=printer,
        open_provider_func=fake_open,
    )

    assert code == 1
    assert "登録できる作業記録がありません" in printer.text


def test_run_reports_submit_failure(json_file):
    from workpulse.attendance.errors import AuthenticationError

    @contextmanager
    def broken():
        raise AuthenticationError("ログイン失敗")
        yield  # pragma: no cover

    printer = Printer()
    code = run(
        ["--date", "2026-09-11", "--json", json_file([RECORD]), "--yes"],
        print_func=printer,
        open_provider_func=broken,
    )

    assert code == 1
    assert "登録に失敗しました" in printer.text
    assert "ログイン失敗" in printer.text


def test_run_prompts_for_date_when_omitted(fake_open, json_file):
    answers = iter(["2026-09-11", "y"])
    code = run(
        ["--json", json_file([RECORD])],
        print_func=Printer(),
        input_func=lambda _: next(answers),
        open_provider_func=fake_open,
    )

    assert code == 0
    assert fake_open.provider.submitted[0].work_date == date(2026, 9, 11)


def _patch_records(monkeypatch, by_day):
    """作業記録の読み込みを差し替える（日付 -> レコード一覧）。"""
    from workpulse.attendance import cli

    monkeypatch.setattr(cli, "load_records", lambda day, _json: by_day.get(day, []))


def test_run_submits_range_and_skips_empty_days(fake_open, monkeypatch):
    _patch_records(
        monkeypatch,
        {date(2026, 9, 11): [RECORD], date(2026, 9, 14): [RECORD, RECORD]},
    )
    printer = Printer()
    code = run(
        ["--date", "2026-09-11~2026-09-14", "--yes"],
        print_func=printer,
        open_provider_func=fake_open,
    )

    assert code == 0
    submitted = fake_open.provider.submitted
    assert [r.work_date for r in submitted] == [date(2026, 9, 11), date(2026, 9, 14)]
    assert len(submitted[1].rows) == 2
    assert "2026-09-12 に登録できる作業記録がありません" in printer.text
    assert "2日分" in printer.text


def test_run_range_asks_confirmation_once(fake_open, monkeypatch):
    _patch_records(monkeypatch, {date(2026, 9, 10): [RECORD], date(2026, 9, 11): [RECORD]})
    prompts = []

    def answer(prompt):
        prompts.append(prompt)
        return "y"

    code = run(
        ["--date", "2026-09-10~2026-09-11"],
        print_func=Printer(),
        input_func=answer,
        open_provider_func=fake_open,
    )

    assert code == 0
    assert len(prompts) == 1
    assert len(fake_open.provider.submitted) == 2


def test_run_range_continues_after_one_day_fails(monkeypatch):
    _patch_records(monkeypatch, {date(2026, 9, 10): [RECORD], date(2026, 9, 11): [RECORD]})

    class HalfBroken(FakeProvider):
        def submit_report(self, report, replace: bool = True):
            if report.work_date == date(2026, 9, 10):
                raise RuntimeError("画面が違う")
            return super().submit_report(report, replace)

    provider = HalfBroken()

    @contextmanager
    def opener():
        yield provider

    printer = Printer()
    code = run(
        ["--date", "2026-09-10~2026-09-11", "--yes"],
        print_func=printer,
        open_provider_func=opener,
    )

    assert code == 1
    assert [r.work_date for r in provider.submitted] == [date(2026, 9, 11)]
    assert "失敗した日: 2026-09-10" in printer.text


def test_run_range_with_no_records_at_all(fake_open, monkeypatch):
    _patch_records(monkeypatch, {})
    code = run(
        ["--date", "2026-09-12~2026-09-13", "--yes"],
        print_func=Printer(),
        open_provider_func=fake_open,
    )

    assert code == 1
    assert fake_open.provider.submitted == []


def test_run_rejects_reversed_range(fake_open):
    printer = Printer()
    code = run(["--date", "2026-09-11~2026-09-10"], print_func=printer, open_provider_func=fake_open)

    assert code == 2
    assert "形式" in printer.text


def test_run_rejects_json_with_range(fake_open, json_file):
    printer = Printer()
    code = run(
        ["--date", "2026-09-10~2026-09-11", "--json", json_file([RECORD])],
        print_func=printer,
        open_provider_func=fake_open,
    )

    assert code == 2
    assert "--json" in printer.text
