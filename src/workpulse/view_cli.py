from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import pandas as pd

from workpulse.detail_code import classify_detail_code
from workpulse.job_code import classify_job_code
from workpulse.parquet_io import read_or_empty
from workpulse.paths import WORK_CONTENT_COLUMNS, work_content_path

# 日報管理アプリへ転記する際の入力項目。作業内容(confirmed_text)と作業時間(duration)
# 以外は自動入力できないため空文字で埋める。業務種別のみ固定値「直接原価」を入れる。
DAILY_REPORT_FIELDS = [
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
DAILY_REPORT_WORK_TYPE = "直接原価"

# 記録が1件も無い日を編集するときに用意する枠の既定の範囲（時）と刻み（分）。
DEFAULT_BLANK_START_HOUR = 9
DEFAULT_BLANK_END_HOUR = 18
SLOT_MINUTES = 30


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


def generate_blank_slots(
    target_date: date,
    start_hour: int = DEFAULT_BLANK_START_HOUR,
    end_hour: int = DEFAULT_BLANK_END_HOUR,
) -> pd.DataFrame:
    """記録が1件も無い日のために、空の30分枠を並べて返す。

    監視ログが取れていない日でも、手入力で日報を作れるようにするためのもの。
    すべて status="missing" とし、内容を確定した枠だけがファイルに保存される。
    """
    rows = []
    cursor = pd.Timestamp(target_date) + pd.Timedelta(hours=start_hour)
    end = pd.Timestamp(target_date) + pd.Timedelta(hours=end_hour)
    while cursor < end:
        rows.append(
            {
                "slot_start": cursor,
                "slot_end": cursor + pd.Timedelta(minutes=SLOT_MINUTES),
                "predicted_text": "",
                "confirmed_text": "",
                "status": "missing",
                "screenshot_path": "",
            }
        )
        cursor += pd.Timedelta(minutes=SLOT_MINUTES)

    return pd.DataFrame(rows, columns=WORK_CONTENT_COLUMNS)


def merge_blank_slots(
    df: pd.DataFrame,
    target_date: date,
    start_hour: int = DEFAULT_BLANK_START_HOUR,
    end_hour: int = DEFAULT_BLANK_END_HOUR,
) -> pd.DataFrame:
    """既存のスロットに空枠を重ねて、既定の時間帯を必ず埋めた一覧を返す。

    既存行がある時間帯はそのまま残し、空いている時間帯だけ空枠で補う。
    """
    blank = generate_blank_slots(target_date, start_hour, end_hour)
    if df.empty:
        return blank

    existing = set(pd.to_datetime(df["slot_start"]))
    blank = blank[~blank["slot_start"].isin(existing)]
    if blank.empty:
        return df

    merged = pd.concat([df, blank], ignore_index=True)
    return merged.sort_values("slot_start").reset_index(drop=True)


def load_slots_for_edit(
    target_date: date,
    fill_blank: bool = False,
    start_hour: int = DEFAULT_BLANK_START_HOUR,
    end_hour: int = DEFAULT_BLANK_END_HOUR,
) -> pd.DataFrame:
    """編集用にスロットを読む。

    記録が1件も無い日は空枠を用意する。`fill_blank=True` のときは
    記録がある日でも既定の時間帯を空枠で埋める（一から作成し始めた日に、
    1件保存した時点で一覧が縮まないようにするため）。
    """
    df = load_slots(target_date)
    if df.empty or fill_blank:
        return merge_blank_slots(df, target_date, start_hour, end_hour)
    return df


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


def build_daily_report_records(
    df: pd.DataFrame,
    classify_job_code_func=classify_job_code,
    classify_detail_code_func=classify_detail_code,
) -> list[dict[str, str]]:
    """作業サマリー（confirmed_text ごとの合計時間）を日報管理アプリの入力形式に変換する。

    各作業サマリーの1行が1レコードに対応する。「業務種別」は固定値「直接原価」、
    「作業内容」に confirmed_text、「作業時間」に HH:MM 形式の合計時間を入れる。
    「ジョブコード」は作業内容から claude haiku（classify_job_code_func）で判定し、
    「詳細コード」は作業内容と判定済みジョブコードから
    claude haiku（classify_detail_code_func）で判定する。
    それ以外の項目は空文字にする。
    """
    summary = compute_work_summary(df)
    records = []
    for text, duration in summary:
        record = {field: "" for field in DAILY_REPORT_FIELDS}
        record["業務種別"] = DAILY_REPORT_WORK_TYPE
        job_code = classify_job_code_func(text)
        record["ジョブコード"] = job_code
        record["詳細コード"] = classify_detail_code_func(text, job_code)
        record["作業時間"] = format_duration(duration)
        record["作業内容"] = text
        records.append(record)
    return records


def format_daily_report_json(
    df: pd.DataFrame,
    classify_job_code_func=classify_job_code,
    classify_detail_code_func=classify_detail_code,
) -> str:
    records = build_daily_report_records(
        df,
        classify_job_code_func=classify_job_code_func,
        classify_detail_code_func=classify_detail_code_func,
    )
    return json.dumps(records, ensure_ascii=False, indent=2)


def update_confirmed_text(
    target_date: date, index: int, new_text: str, fill_blank: bool = False
) -> None:
    """index は load_slots() が返す一覧（欠落枠を含む）上の位置。

    欠落枠（ファイルに未保存の枠）が選択された場合は、その枠を新規行として
    ファイルに追加する。既存行が選択された場合は従来どおり更新する。
    記録が1件も無い日は空枠の一覧を基準にする。
    """
    display_df = load_slots_for_edit(target_date, fill_blank=fill_blank)
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
    # 監視ログが無い日は保存先ディレクトリも無いので作ってから書く。
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def run_interactive(target_date: date, input_func=input, print_func=print) -> None:
    df = load_slots_for_edit(target_date)
    if df.empty:
        print_func(f"{target_date.isoformat()} の記録はありません")
        return

    # 監視ログが無い日は空枠から作り始める。保存しても一覧が縮まないよう、
    # 以降の再読込でも空枠を埋め続ける。
    started_blank = bool((df["status"] == "missing").all())
    if started_blank:
        print_func(f"{target_date.isoformat()} の記録はありません。新規に作成します")

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
            update_confirmed_text(target_date, index, new_text, fill_blank=started_blank)
            df = load_slots_for_edit(target_date, fill_blank=started_blank)
            print_func("保存しました")
        print_func(format_slot_line(index, df.loc[index]))

    for line in format_summary_lines(df):
        print_func(line)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="作業内容の閲覧・編集")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--summary",
        action="store_true",
        help="対話プロンプトを開かず、指定日の作業サマリーのみを出力して終了する",
    )
    parser.add_argument(
        "--daily-report-json",
        action="store_true",
        help="対話プロンプトを開かず、指定日の作業サマリーを日報管理アプリ入力形式のJSONで出力して終了する",
    )
    return parser.parse_args(argv)


def parse_target_date(argv: list[str]) -> date:
    """後方互換用。--date のみをパースして date を返す。"""
    return date.fromisoformat(parse_args(argv).date)


def print_summary(target_date: date, print_func=print) -> None:
    """指定日のサマリーのみを非対話で出力する（欠落枠を含む集計）。"""
    df = load_slots(target_date)
    if df.empty:
        print_func(f"{target_date.isoformat()} の記録はありません")
        return
    lines = format_summary_lines(df)
    if not lines:
        print_func(f"{target_date.isoformat()} の確定済み作業内容はありません")
        return
    for line in lines:
        print_func(line)


def print_daily_report_json(
    target_date: date,
    print_func=print,
    classify_job_code_func=classify_job_code,
    classify_detail_code_func=classify_detail_code,
) -> None:
    """指定日の作業サマリーを日報管理アプリ入力形式のJSONで非対話出力する。"""
    df = load_slots(target_date)
    print_func(
        format_daily_report_json(
            df,
            classify_job_code_func=classify_job_code_func,
            classify_detail_code_func=classify_detail_code_func,
        )
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    target_date = date.fromisoformat(args.date)
    if args.daily_report_json:
        print_daily_report_json(target_date)
    elif args.summary:
        print_summary(target_date)
    else:
        run_interactive(target_date)
