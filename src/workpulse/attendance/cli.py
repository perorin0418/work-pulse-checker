# src/workpulse/attendance/cli.py
"""日報登録の CLI。

`submit_report.bat` から呼ばれる想定。指定日の作業記録
（`view.py --daily-report-json` と同じ9項目）を勤怠サービスへ登録する。

    python submit_report.py --date 2026-09-11
    python submit_report.py --date 2026-09-11 --dry-run
    python submit_report.py --date 2026-09-11 --json records.json

`--date` を省略すると対話で入力を促す（bat のダブルクリック起動用）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from workpulse.attendance.models import DailyReport
from workpulse.attendance.report_format import rows_from_records


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="指定日の作業記録を勤怠サービスの日報に登録する")
    parser.add_argument("--date", help="YYYY-MM-DD（省略時は対話で入力）")
    parser.add_argument(
        "--json",
        dest="json_path",
        help="日報レコードのJSONファイル。省略時はその日の作業記録から生成する",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="登録せず、送信する内容だけを表示する",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="既存の行を残して追記する（既定は置き換え）",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="確認を省略して登録する",
    )
    return parser.parse_args(argv)


def resolve_date(text: str | None, input_func=input, today: date | None = None) -> date:
    """日付を決める。未指定なら対話で聞く。

    空入力なら前営業日（月曜なら金曜、それ以外は前日）を使う。
    """
    if text:
        return date.fromisoformat(text)

    today = today or date.today()
    default = previous_workday(today)
    answer = input_func(f"対象日を入力してください [YYYY-MM-DD] (既定: {default}): ").strip()
    if not answer:
        return default
    return date.fromisoformat(answer)


def previous_workday(today: date) -> date:
    """前営業日を返す（土日を飛ばす）。"""
    day = today - timedelta(days=1)
    while day.weekday() >= 5:  # 5=土, 6=日
        day -= timedelta(days=1)
    return day


def load_records(target_date: date, json_path: str | None) -> list[dict[str, str]]:
    """登録する日報レコードを用意する。

    `--json` があればそのファイルを読み、無ければその日の作業記録から作る。
    """
    if json_path:
        return json.loads(Path(json_path).read_text(encoding="utf-8"))

    from workpulse.view_cli import build_daily_report_records, load_slots

    return build_daily_report_records(load_slots(target_date))


def format_preview(target_date: date, records: list[dict[str, str]]) -> str:
    """登録内容を人が読める形に整える。"""
    lines = [f"■ {target_date.isoformat()} に登録する内容（{len(records)}件）"]
    for i, record in enumerate(records, 1):
        lines.append(f"--- {i} ---")
        lines.append(f"  業務種別    : {record.get('業務種別', '')}")
        lines.append(f"  ジョブコード: {record.get('ジョブコード', '')}")
        lines.append(f"  作業時間    : {record.get('作業時間', '')}")
        for field in ("詳細コード", "作業場所", "作業内容", "状況", "保留・宿題事項", "課題・悩み"):
            lines.append(f"  {field:<12}: {record.get(field, '')}")
    return "\n".join(lines)


def run(
    argv: list[str],
    print_func=print,
    input_func=input,
    open_provider_func=None,
) -> int:
    """CLI 本体。戻り値はプロセスの終了コード。"""
    args = parse_args(argv)

    try:
        target_date = resolve_date(args.date, input_func=input_func)
    except ValueError:
        print_func("日付の形式が正しくありません（例: 2026-09-11）")
        return 2

    records = load_records(target_date, args.json_path)
    if not records:
        print_func(f"{target_date.isoformat()} に登録できる作業記録がありません")
        return 1

    print_func(format_preview(target_date, records))

    if args.dry_run:
        print_func("\n--dry-run のため登録しません")
        return 0

    if not args.yes:
        answer = input_func("\nこの内容で登録しますか？ [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            print_func("中止しました")
            return 1

    if open_provider_func is None:
        from workpulse.attendance.service import open_provider as open_provider_func

    report = DailyReport(work_date=target_date, rows=rows_from_records(records))
    try:
        with open_provider_func() as provider:
            result = provider.submit_report(report, replace=not args.append)
    except Exception as exc:  # 認証失敗・画面変更などをまとめて拾う
        print_func(f"登録に失敗しました: {type(exc).__name__}: {exc}")
        return 1

    print_func(f"登録しました: {result.work_date} ({len(report.rows)}件)")
    return 0


def main(argv: list[str] | None = None) -> None:
    code = run(argv if argv is not None else sys.argv[1:])
    sys.exit(code)
