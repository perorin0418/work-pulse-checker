# tests/test_view_launcher.py
"""ダブルクリック起動用の view ランチャーのテスト。"""
from __future__ import annotations

from datetime import date

import pytest

from workpulse.view_launcher import build_argv, main


def test_build_argv_prompts_when_date_missing():
    argv = build_argv([], input_func=lambda _: "2026-09-11")
    assert argv == ["--date", "2026-09-11"]


def test_build_argv_defaults_to_previous_workday():
    argv = build_argv([], input_func=lambda _: "", today=date(2026, 9, 14))
    assert argv == ["--date", "2026-09-11"]  # 月曜 -> 金曜


def test_build_argv_keeps_existing_date():
    argv = build_argv(["--date", "2026-09-01", "--summary"], input_func=_never_called)
    assert argv == ["--date", "2026-09-01", "--summary"]


def test_build_argv_passes_other_options_through():
    argv = build_argv(["--summary"], input_func=lambda _: "2026-09-11")
    assert argv == ["--date", "2026-09-11", "--summary"]


def test_build_argv_rejects_bad_date():
    with pytest.raises(ValueError):
        build_argv([], input_func=lambda _: "2026/09/11")


def test_main_exits_with_code_2_on_bad_date(monkeypatch, capsys):
    # 既定引数で束縛済みの input を差し替えられないので build_argv を包む。
    monkeypatch.setattr(
        "workpulse.view_launcher.build_argv",
        lambda argv: build_argv(argv, input_func=lambda _: "abc"),
    )
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
    assert "日付の形式" in capsys.readouterr().out


def test_main_delegates_to_view_cli(monkeypatch):
    called = []
    monkeypatch.setattr("workpulse.view_launcher.view_main", lambda argv: called.append(argv))

    main(["--date", "2026-09-11", "--summary"])

    assert called == [["--date", "2026-09-11", "--summary"]]


def _never_called(prompt):  # pragma: no cover - 呼ばれたら失敗
    raise AssertionError("日付が指定済みなら入力を求めないこと")
