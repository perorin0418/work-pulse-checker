# src/workpulse/attendance/report_format.py
"""日報レコード（9項目）と `ReportRow` の相互変換。

`view_cli.DAILY_REPORT_FIELDS` が出す辞書を、勤怠サービスに登録できる
`ReportRow` に直す。画面との対応は次のとおり。

| 日報レコード | HRMOS 日報の欄 |
| --- | --- |
| 業務種別 | 業務（上段のセレクト） |
| ジョブコード | 業務（下段のテキスト） |
| 作業時間 | 業務時間(実績) |
| 詳細コード・作業場所・作業内容・状況・保留・宿題事項・課題・悩み | 備考 |

業務時間(予定) は入力しない。備考は `【項目名】値` を1行ずつ並べる。
"""
from __future__ import annotations

from workpulse.attendance.models import ReportRow

#: 備考欄に `【項目名】値` の形で並べる項目。順序がそのまま表示順になる。
NOTE_FIELDS = [
    "詳細コード",
    "作業場所",
    "作業内容",
    "状況",
    "保留・宿題事項",
    "課題・悩み",
]

#: 値が空のときに備考へ入れる文字列。
EMPTY_PLACEHOLDER = "なし"

#: 空欄のときに補完せず、そのまま空で出す項目。
KEEP_EMPTY_FIELDS = frozenset({"状況"})


def build_note(record: dict[str, str], placeholder: str = EMPTY_PLACEHOLDER) -> str:
    """備考欄の文字列を組み立てる。

        【詳細コード】Z-02
        【作業場所】自宅（リモート）
        ...

    空欄は `placeholder`（既定「なし」）で補うが、`KEEP_EMPTY_FIELDS` の
    項目（状況）は空欄のままにする。
    """
    lines = []
    for field in NOTE_FIELDS:
        value = str(record.get(field, "") or "").strip()
        if not value and field not in KEEP_EMPTY_FIELDS:
            value = placeholder
        lines.append(f"【{field}】{value}")
    return "\n".join(lines)


def parse_note(note: str) -> dict[str, str]:
    """`build_note()` が作った備考を辞書に戻す。

    `【項目名】` で始まらない行は直前の項目の続き（複数行の値）とみなす。
    """
    parsed: dict[str, str] = {}
    current = ""
    for line in (note or "").splitlines():
        if line.startswith("【") and "】" in line:
            name, _, value = line[1:].partition("】")
            current = name
            parsed[current] = value.strip()
        elif current:
            parsed[current] = (parsed[current] + "\n" + line).strip()
    return parsed


def record_to_row(record: dict[str, str], placeholder: str = EMPTY_PLACEHOLDER) -> ReportRow:
    """日報レコード1件を `ReportRow` に変換する。"""
    return ReportRow(
        category=str(record.get("業務種別", "") or "").strip(),
        service_name=str(record.get("ジョブコード", "") or "").strip(),
        plan_minutes=None,  # 業務時間(予定) は入力しない
        result_minutes=parse_duration(record.get("作業時間", "")),
        note=build_note(record, placeholder=placeholder),
    )


def rows_from_records(
    records: list[dict[str, str]], placeholder: str = EMPTY_PLACEHOLDER
) -> list[ReportRow]:
    """日報レコードの一覧を `ReportRow` の一覧にする。"""
    return [record_to_row(r, placeholder=placeholder) for r in records]


def row_to_record(row: ReportRow) -> dict[str, str]:
    """`ReportRow` を日報レコードに戻す（取得内容の確認用）。"""
    record = {
        "業務種別": row.category,
        "ジョブコード": row.service_name,
        "作業時間": format_duration(row.result_minutes),
    }
    parsed = parse_note(row.note)
    for field in NOTE_FIELDS:
        record[field] = parsed.get(field, "")
    return record


def parse_duration(text: str) -> int | None:
    """"03:36" を分（216）にする。空や不正な値は None。"""
    text = str(text or "").strip()
    if ":" not in text:
        return None
    hours, _, minutes = text.partition(":")
    try:
        total = int(hours) * 60 + int(minutes)
    except ValueError:
        return None
    return total or None


def format_duration(minutes: int | None) -> str:
    """分を "03:36" 形式にする。None は空文字。"""
    if not minutes or minutes < 0:
        return ""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
