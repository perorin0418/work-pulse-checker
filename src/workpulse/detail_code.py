from __future__ import annotations

import re
import subprocess
import sys
from typing import Callable, Optional

from workpulse.job_code import JOB_CODE_ANCILLARY, JOB_CODE_COMMON

# 【基盤開発課】作業詳細コード_20250701~.xlsx「ジョブコード詳細（基盤開発課）」より。
# ジョブコードごとに選択可能な詳細コードと、その意味（判定用の説明）を定義する。
DETAIL_CODES: dict[str, list[tuple[str, str]]] = {
    JOB_CODE_ANCILLARY: [
        ("Z-01", "会社行事（方針説明会、実施計画発表会、弔事等）"),
        ("Z-02", "会議体直接PJ以外（事業部会、部会、課会、朝会等の定例会議）"),
        ("Z-04", "研修（社内外研修の受講、研修報告書作成）"),
        ("Z-05", "一般事務（社内OA操作、日報入力、庶務、社内各種調査等）"),
        ("Z-06", "健康経営活動（健康診断受診含む）"),
        ("Z-99", "部・課管理（進捗・工数・勤怠・予算・目標管理、評価、1on1ミーティング）"),
    ],
    JOB_CODE_COMMON: [
        ("A-90", "品質向上活動"),
        ("A-91", "障害分析"),
        ("A-92", "各社協議、説明会への参加"),
        ("A-93", "是正、ふりかえり"),
        ("A-94", "開発・業務スキル習得のための活動（勉強会、e-learningや動画視聴等による学習）"),
        ("A-95", "ISO活動（ISO委員会、セルフチェック等）"),
        ("B-10", "課題・QA対応（工程が特定できないもの）"),
        ("B-11", "課題・QA対応_システム要件定義(RD)"),
        ("B-12", "課題・QA対応_設計工程(UI-SS)"),
        ("B-13", "課題・QA対応_プログラム構造設計(PS)プログラミング(PG)プログラミングテスト(PT)"),
        ("B-14", "課題・QA対応_結合テスト(IT)"),
    ],
}

# 判定できない場合のフォールバック。日報上で最も無難な区分を選ぶ。
DETAIL_CODE_FALLBACK: dict[str, str] = {
    JOB_CODE_ANCILLARY: "Z-05",
    JOB_CODE_COMMON: "B-10",
}

_CODE_PATTERN = re.compile(r"[A-Z]-\d{2}")


def build_detail_code_prompt(work_text: str, job_code: str) -> str:
    candidates = DETAIL_CODES.get(job_code, [])
    candidate_lines = "\n".join(f"{code}: {label}" for code, label in candidates)
    return (
        "あなたは社内の日報の作業詳細コードを判定するアシスタントです。\n"
        f"ジョブコード「{job_code}」で選択できる詳細コードは次のとおりです。\n"
        f"{candidate_lines}\n\n"
        f"作業内容: {work_text}\n\n"
        "この作業内容に最も適切な詳細コードを1つ選び、コード（例: Z-05）だけを"
        "他の文字を含めずに出力してください。判断できない場合も必ずいずれか1つを選んでください。"
    )


def _default_run_command(cmd: list[str]) -> subprocess.CompletedProcess:
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


def classify_detail_code(
    work_text: str,
    job_code: str,
    run_command: Optional[Callable[[list[str]], subprocess.CompletedProcess]] = None,
) -> str:
    """作業内容とジョブコードから詳細コードを判定する。

    作業内容は表記ゆれがあり機械的な文字列一致では判定できないため、
    claude -p --model haiku による意味的判定に委ねる。
    呼び出し失敗・判定不能時はジョブコードごとのフォールバックコードを返す。
    未知のジョブコードの場合は空文字を返す。
    """
    candidates = DETAIL_CODES.get(job_code)
    if not candidates:
        return ""

    fallback = DETAIL_CODE_FALLBACK.get(job_code, "")
    if not work_text or not work_text.strip():
        return fallback

    if run_command is None:
        run_command = _default_run_command

    prompt_text = build_detail_code_prompt(work_text, job_code)
    try:
        result = run_command(["claude", "-p", prompt_text, "--model", "haiku"])
    except Exception:
        return fallback

    if result.returncode != 0:
        return fallback
    if result.stdout is None:
        return fallback

    valid_codes = {code for code, _ in candidates}
    for token in _CODE_PATTERN.findall(result.stdout.strip().upper()):
        if token in valid_codes:
            return token
    return fallback
