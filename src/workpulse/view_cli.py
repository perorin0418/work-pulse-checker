from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from workpulse.parquet_io import read_or_empty
from workpulse.paths import WORK_CONTENT_COLUMNS, work_content_path


def load_slots(target_date: date) -> pd.DataFrame:
    return read_or_empty(work_content_path(target_date), WORK_CONTENT_COLUMNS)


def format_slot_line(index: int, row: pd.Series) -> str:
    slot_start = pd.Timestamp(row["slot_start"]).strftime("%H:%M")
    slot_end = pd.Timestamp(row["slot_end"]).strftime("%H:%M")
    return f"[{index}] {slot_start}-{slot_end} ({row['status']}) {row['confirmed_text']}"


def update_confirmed_text(target_date: date, index: int, new_text: str) -> None:
    path = work_content_path(target_date)
    df = read_or_empty(path, WORK_CONTENT_COLUMNS)
    if index < 0 or index >= len(df):
        raise IndexError(f"invalid slot index: {index}")
    df.loc[index, "confirmed_text"] = new_text
    df.loc[index, "status"] = "confirmed"
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


def parse_target_date(argv: list[str]) -> date:
    parser = argparse.ArgumentParser(description="作業内容の閲覧・編集")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    return date.fromisoformat(args.date)


def main(argv: list[str] | None = None) -> None:
    target_date = parse_target_date(argv if argv is not None else sys.argv[1:])
    run_interactive(target_date)
