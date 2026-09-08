from __future__ import annotations

import subprocess
import sys
from typing import Callable, Optional

# 付帯作業とみなす作業内容の代表例。表記ゆれ（「朝会に参加」等）もあるため、
# 単純な文字列一致ではなく claude haiku に意味的に判定させる。
ANCILLARY_WORK_TYPES = ["朝会", "課会", "部会", "日報入力", "庶務", "1on1ミーティング"]

JOB_CODE_ANCILLARY = "2502046_【C25】標準準拠システム保守付帯作業"
JOB_CODE_COMMON = "2502044_【C25】標準準拠システム保守（共通機能）"


def build_classification_prompt(work_text: str) -> str:
    types_text = "、".join(ANCILLARY_WORK_TYPES)
    return (
        "あなたは社内の作業内容を分類するアシスタントです。\n"
        f"次の作業内容が「{types_text}」のいずれか（表記ゆれ・類似表現を含む）に該当するかを判定してください。\n"
        f"作業内容: {work_text}\n"
        "該当する場合は `yes`、該当しない場合は `no` とだけ、他の文字を含めずに出力してください。"
    )


def classify_job_code(
    work_text: str,
    run_command: Optional[Callable[[list[str]], subprocess.CompletedProcess]] = None,
) -> str:
    """作業内容(confirmed_text)からジョブコードを判定する。

    「朝会、課会、部会、日報入力、庶務、1on1ミーティング」に該当する場合は
    付帯作業のジョブコード、それ以外は共通機能のジョブコードを返す。
    該当有無の判定は表記ゆれを含むため、機械的な文字列一致ではなく
    claude -p --model haiku による意味的判定に委ねる。
    呼び出し失敗・判定不能時は安全側として共通機能のジョブコードにフォールバックする。
    """
    if not work_text or not work_text.strip():
        return JOB_CODE_COMMON

    if run_command is None:
        def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
            kwargs = {
                "capture_output": True,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "timeout": 60,
                "stdin": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            return subprocess.run(cmd, **kwargs)

    prompt_text = build_classification_prompt(work_text)
    try:
        result = run_command(["claude", "-p", prompt_text, "--model", "haiku"])
    except Exception:
        return JOB_CODE_COMMON

    if result.returncode != 0:
        return JOB_CODE_COMMON
    if result.stdout is None:
        return JOB_CODE_COMMON

    answer = result.stdout.strip().lower()
    if answer.startswith("yes"):
        return JOB_CODE_ANCILLARY
    return JOB_CODE_COMMON
