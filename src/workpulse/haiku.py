from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence


def build_prompt_text(
    summary_text: str,
    screenshot_path: Path,
    today_history: Sequence[str] = (),
) -> str:
    history_section = ""
    if today_history:
        history_lines = "\n".join(f"- {text}" for text in today_history)
        history_section = (
            "\n本日すでに記録された作業内容（参考。同じ作業の継続なら近い表現を使ってよい）:\n"
            f"{history_lines}\n"
        )

    return (
        "あなたはユーザーの直近30分間のPC作業内容を1行で推定するアシスタントです。\n"
        f"画面スクリーンショット: {screenshot_path}\n"
        f"{summary_text}\n"
        f"{history_section}"
        "上記のスクリーンショットと操作ログから、ユーザーが直近30分間に行っていた作業内容を"
        "日本語で1行、簡潔に推定してください。推定した作業内容の文だけを出力してください。"
    )


def predict_work_content(
    summary_text: str,
    screenshot_path: Path,
    run_command: Optional[Callable[[list[str]], subprocess.CompletedProcess]] = None,
    today_history: Sequence[str] = (),
) -> str:
    if run_command is None:
        def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
            kwargs = {
                "capture_output": True,
                "text": True,
                "timeout": 60,
                "stdin": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            return subprocess.run(cmd, **kwargs)

    prompt_text = build_prompt_text(summary_text, screenshot_path, today_history=today_history)
    try:
        result = run_command(["claude", "-p", prompt_text, "--model", "haiku"])
    except Exception:
        return ""

    if result.returncode != 0:
        return ""
    if result.stdout is None:
        return ""
    return result.stdout.strip()
