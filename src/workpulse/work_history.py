# src/workpulse/work_history.py
from __future__ import annotations

from datetime import date

from workpulse.parquet_io import read_or_empty
from workpulse.paths import WORK_CONTENT_COLUMNS, work_content_path


def recent_confirmed_texts(target_date: date, limit: int = 8) -> list[str]:
    """指定日の work-content.parquet から確定済みテキストを新しい順・重複除去で返す。

    確認ダイアログの再利用ボタンと、Haiku へのプロンプトで
    「本日すでに記録した作業内容」として渡すために使う。
    """
    df = read_or_empty(work_content_path(target_date), WORK_CONTENT_COLUMNS)
    if df.empty:
        return []

    # slot_start が新しい順に並べ、confirmed_text が空でない行だけを対象にする。
    ordered = df.sort_values("slot_start", ascending=False)

    seen: set[str] = set()
    result: list[str] = []
    for text in ordered["confirmed_text"]:
        text = (text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break

    return result
