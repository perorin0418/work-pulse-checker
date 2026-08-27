# src/workpulse/prompt_main.py
from __future__ import annotations

import sys
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from workpulse.audit_summary import summarize
from workpulse.confirm_ui import run_confirm_dialog
from workpulse.countdown_ui import run_countdown_window
from workpulse.haiku import predict_work_content
from workpulse.parquet_io import append_row, read_or_empty
from workpulse.paths import AUDIT_COLUMNS, WORK_CONTENT_COLUMNS, audit_path, work_content_path
from workpulse.screenshot import capture_png_bytes_mss, try_save_screenshot
from workpulse.work_history import recent_confirmed_texts


def slot_bounds(now: datetime) -> tuple[datetime, datetime]:
    """now を起点に「直前に終わった30分枠」の開始・終了時刻を返す。

    30分間隔タスクは各枠の終了直後（例: 14:30）に起動される想定。
    そのため slot_end は now 以下で直近の30分境界に切り捨て、
    slot_start はその30分前とする（例: now=14:30 -> 14:00〜14:30）。
    """
    minute = 0 if now.minute < 30 else 30
    slot_end = now.replace(minute=minute, second=0, microsecond=0)
    slot_start = slot_end - timedelta(minutes=30)
    return slot_start, slot_end


def build_work_content_row(
    slot_start: datetime,
    slot_end: datetime,
    predicted_text: str,
    confirmed_text: str,
    status: str,
    screenshot_path: Path | None,
) -> dict:
    return {
        "slot_start": slot_start,
        "slot_end": slot_end,
        "predicted_text": predicted_text,
        "confirmed_text": confirmed_text,
        "status": status,
        "screenshot_path": str(screenshot_path) if screenshot_path is not None else "",
    }


def run() -> None:
    now = datetime.now()
    slot_start, slot_end = slot_bounds(now)

    # カウントダウン表示中にスクリーンショット撮影とAI推定をバックグラウンドで
    # 完了させておく。直列にすると推定完了までダイアログ表示が数秒〜数十秒
    # 遅延するため、カウントダウンの待ち時間を無駄なく使う。
    prep_result: dict = {}

    def prepare_prediction() -> None:
        shot_path = try_save_screenshot(now, capture_png_bytes_mss)

        audit_df = read_or_empty(audit_path(now.date()), AUDIT_COLUMNS)
        summary_text = summarize(audit_df, now)

        today_history = recent_confirmed_texts(now.date())

        if shot_path is not None:
            predicted_text = predict_work_content(summary_text, shot_path, today_history=today_history)
        else:
            predicted_text = ""

        prep_result["shot_path"] = shot_path
        prep_result["predicted_text"] = predicted_text
        prep_result["today_history"] = today_history

    prep_thread = threading.Thread(target=prepare_prediction, daemon=True)
    prep_thread.start()

    run_countdown_window(30)

    # カウントダウン(30秒)より予測処理が長引いた場合のみ、ここで待つ。
    prep_thread.join()

    shot_path = prep_result["shot_path"]
    predicted_text = prep_result["predicted_text"]
    today_history = prep_result["today_history"]

    confirmed_text, status = run_confirm_dialog(
        predicted_text, timeout_seconds=300, history=today_history
    )

    row = build_work_content_row(slot_start, slot_end, predicted_text, confirmed_text, status, shot_path)
    append_row(work_content_path(now.date()), row, WORK_CONTENT_COLUMNS)


def main() -> None:
    try:
        run()
    except Exception:
        log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "prompt_error.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        sys.exit(1)
