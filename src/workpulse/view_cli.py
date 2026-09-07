from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from workpulse.parquet_io import read_or_empty
from workpulse.paths import WORK_CONTENT_COLUMNS, work_content_path


def generate_missing_slots(df: pd.DataFrame) -> pd.DataFrame:
    """記録済みスロットの最初〜最後の範囲内で、記録が抜けている30分枠を補完行として返す。

    例: 10:00-11:30 と 13:30-17:00 に記録があり、11:30-13:30 に記録がない場合、
    11:30, 12:00, 12:30, 13:00 の4枠を status="missing" として返す。
    範囲の外側（最初の記録より前・最後の記録より後）は対象外。
    """
    if len(df) < 2:
        return df.iloc[0:0]

    starts = pd.to_datetime(df["slot_start"])
    existing = set(starts)
    range_start = starts.min()
    range_end = pd.to_datetime(df["slot_end"]).max()

    missing_rows = []
    cursor = range_start
    while cursor < range_end:
        if cursor not in existing:
            missing_rows.append(
                {
                    "slot_start": cursor,
                    "slot_end": cursor + pd.Timedelta(minutes=30),
                    "predicted_text": "",
                    "confirmed_text": "",
                    "status": "missing",
                    "screenshot_path": "",
                }
            )
        cursor += pd.Timedelta(minutes=30)

    return pd.DataFrame(missing_rows, columns=WORK_CONTENT_COLUMNS)


def load_slots(target_date: date) -> pd.DataFrame:
    """指定日のスロットを、記録が抜けている時間帯(status="missing")も補完して返す。"""
    df = read_or_empty(work_content_path(target_date), WORK_CONTENT_COLUMNS)
    if df.empty:
        return df

    df = df.copy()
    df["slot_start"] = pd.to_datetime(df["slot_start"])
    df["slot_end"] = pd.to_datetime(df["slot_end"])

    missing = generate_missing_slots(df)
    if not missing.empty:
        df = pd.concat([df, missing], ignore_index=True)

    return df.sort_values("slot_start").reset_index(drop=True)


def format_slot_line(index: int, row: pd.Series) -> str:
    slot_start = pd.Timestamp(row["slot_start"]).strftime("%H:%M")
    slot_end = pd.Timestamp(row["slot_end"]).strftime("%H:%M")
    return f"[{index}] {slot_start}-{slot_end} ({row['status']}) {row['confirmed_text']}"


def format_duration(duration: pd.Timedelta) -> str:
    total_minutes = int(duration.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02d}:{minutes:02d}"


def compute_work_summary(df: pd.DataFrame) -> list[tuple[str, pd.Timedelta]]:
    """confirmed_text ごとの合計実施時間を、実施時間が長い順に返す。"""
    if df.empty:
        return []

    work = df.copy()
    work["confirmed_text"] = work["confirmed_text"].fillna("").astype(str).str.strip()
    work = work[work["confirmed_text"] != ""]
    if work.empty:
        return []

    duration = pd.to_datetime(work["slot_end"]) - pd.to_datetime(work["slot_start"])
    totals = duration.groupby(work["confirmed_text"]).sum()
    totals = totals.sort_values(ascending=False)
    return list(totals.items())


def format_summary_lines(df: pd.DataFrame) -> list[str]:
    summary = compute_work_summary(df)
    if not summary:
        return []

    lines = ["--- 作業サマリー ---"]
    for text, duration in summary:
        lines.append(f"{format_duration(duration)}  {text}")
    total = sum((duration for _, duration in summary), pd.Timedelta(0))
    lines.append(f"合計: {format_duration(total)}")
    return lines


def update_confirmed_text(target_date: date, index: int, new_text: str) -> None:
    """index は load_slots() が返す一覧（欠落枠を含む）上の位置。

    欠落枠（ファイルに未保存の枠）が選択された場合は、その枠を新規行として
    ファイルに追加する。既存行が選択された場合は従来どおり更新する。
    """
    display_df = load_slots(target_date)
    if index < 0 or index >= len(display_df):
        raise IndexError(f"invalid slot index: {index}")

    slot_start = display_df.loc[index, "slot_start"]
    slot_end = display_df.loc[index, "slot_end"]

    path = work_content_path(target_date)
    df = read_or_empty(path, WORK_CONTENT_COLUMNS)
    if not df.empty:
        df["slot_start"] = pd.to_datetime(df["slot_start"])

    match = df.index[df["slot_start"] == slot_start] if not df.empty else df.index[:0]
    if len(match) > 0:
        raw_index = match[0]
        df.loc[raw_index, "confirmed_text"] = new_text
        df.loc[raw_index, "status"] = "confirmed"
    else:
        new_row = pd.DataFrame(
            [
                {
                    "slot_start": slot_start,
                    "slot_end": slot_end,
                    "predicted_text": "",
                    "confirmed_text": new_text,
                    "status": "confirmed",
                    "screenshot_path": "",
                }
            ],
            columns=WORK_CONTENT_COLUMNS,
        )
        df = pd.concat([df, new_row], ignore_index=True)

    df = df.sort_values("slot_start").reset_index(drop=True)
    df.to_parquet(path, index=False)


def run_interactive(target_date: date, input_func=input, print_func=print) -> None:
    df = load_slots(target_date)
    if df.empty:
        print_func(f"{target_date.isoformat()} の記録はありません")
        return

    for i, row in df.iterrows():
        print_func(format_slot_line(i, row))

    print_func("編集する番号を入力してください（何も入力せず終了する場合はEnter）")
    while True:
        selection = input_func("> ").strip()
        if selection == "":
            break
        if not selection.isdigit() or int(selection) not in df.index:
            print_func("無効な番号です")
            continue

        index = int(selection)
        current = df.loc[index, "confirmed_text"]
        print_func(f"現在の内容: {current}")
        new_text = input_func("新しい内容（そのまま変更しない場合はEnter）: ").strip()
        if new_text != "":
            update_confirmed_text(target_date, index, new_text)
            df = load_slots(target_date)
            print_func("保存しました")
        print_func(format_slot_line(index, df.loc[index]))

    for line in format_summary_lines(df):
        print_func(line)


def parse_target_date(argv: list[str]) -> date:
    parser = argparse.ArgumentParser(description="作業内容の閲覧・編集")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    return date.fromisoformat(args.date)


def main(argv: list[str] | None = None) -> None:
    target_date = parse_target_date(argv if argv is not None else sys.argv[1:])
    run_interactive(target_date)
