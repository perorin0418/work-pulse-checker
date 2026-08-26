from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def recent_rows(df: pd.DataFrame, now: datetime, window_minutes: int = 30) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = now - timedelta(minutes=window_minutes)
    return df[df["timestamp"] >= cutoff]


def summarize(df: pd.DataFrame, now: datetime, window_minutes: int = 30, top_n: int = 3) -> str:
    recent = recent_rows(df, now, window_minutes)
    if recent.empty:
        return f"直近{window_minutes}分間の操作記録なし"

    top_titles = recent["foreground_window_title"].value_counts().head(top_n)
    top_processes = recent["foreground_process_name"].value_counts().head(top_n)

    titles_text = ", ".join(f"{name}({count})" for name, count in top_titles.items() if name)
    processes_text = ", ".join(f"{name}({count})" for name, count in top_processes.items() if name)

    return (
        f"直近{window_minutes}分間のよく使われたウィンドウ: {titles_text or 'なし'}\n"
        f"直近{window_minutes}分間のよく使われたプロセス: {processes_text or 'なし'}"
    )
