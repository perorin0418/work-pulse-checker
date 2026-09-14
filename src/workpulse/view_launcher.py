# src/workpulse/view_launcher.py
"""`view.py` をダブルクリック起動から使うための入口。

`view.py` は `--date` が必須なので、bat から起動したときは対象日を
対話で聞いてから `view_cli.main()` に渡す。日付を明示した場合や
`--summary` などのオプションはそのまま `view_cli` に素通しする。
"""
from __future__ import annotations

import sys
from datetime import date

from workpulse.attendance.cli import resolve_date
from workpulse.view_cli import main as view_main


def build_argv(argv: list[str], input_func=input, today: date | None = None) -> list[str]:
    """`view_cli.main()` に渡す引数を組み立てる。

    `--date` が無ければ対話で聞いて補う。空入力なら前営業日。
    """
    if "--date" in argv:
        return list(argv)

    target_date = resolve_date(None, input_func=input_func, today=today)
    return ["--date", target_date.isoformat(), *argv]


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    try:
        resolved = build_argv(argv)
    except ValueError:
        print("日付の形式が正しくありません（例: 2026-09-11）")
        sys.exit(2)
    view_main(resolved)
