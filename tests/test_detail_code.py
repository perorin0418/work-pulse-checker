import subprocess

from workpulse.detail_code import (
    DETAIL_CODES,
    build_detail_code_prompt,
    classify_detail_code,
)
from workpulse.job_code import JOB_CODE_ANCILLARY, JOB_CODE_COMMON


def test_build_detail_code_prompt_lists_candidates_for_job_code():
    text = build_detail_code_prompt("朝会", JOB_CODE_ANCILLARY)
    assert "朝会" in text
    assert "Z-02" in text
    assert "Z-99" in text
    assert "B-10" not in text


def test_build_detail_code_prompt_lists_common_candidates():
    text = build_detail_code_prompt("資料作成", JOB_CODE_COMMON)
    assert "B-13" in text
    assert "A-94" in text
    assert "Z-01" not in text


def test_classify_detail_code_returns_code_from_haiku_answer():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Z-02\n", stderr="")

    assert classify_detail_code("朝会", JOB_CODE_ANCILLARY, run_command=fake_run) == "Z-02"


def test_classify_detail_code_extracts_code_from_verbose_answer():
    def fake_run(cmd):
        return subprocess.CompletedProcess(
            args=cmd, returncode=0, stdout="答えは B-13 です。", stderr=""
        )

    assert classify_detail_code("実装作業", JOB_CODE_COMMON, run_command=fake_run) == "B-13"


def test_classify_detail_code_rejects_code_not_in_candidates():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Z-01", stderr="")

    # 共通機能のジョブコードに Z 系は存在しないためフォールバックする
    assert classify_detail_code("実装作業", JOB_CODE_COMMON, run_command=fake_run) == "B-10"


def test_classify_detail_code_falls_back_on_nonzero_exit():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

    assert classify_detail_code("朝会", JOB_CODE_ANCILLARY, run_command=fake_run) == "Z-05"


def test_classify_detail_code_falls_back_on_exception():
    def fake_run(cmd):
        raise FileNotFoundError("claude command not found")

    assert classify_detail_code("資料作成", JOB_CODE_COMMON, run_command=fake_run) == "B-10"


def test_classify_detail_code_falls_back_when_stdout_is_none():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=None, stderr=None)

    assert classify_detail_code("朝会", JOB_CODE_ANCILLARY, run_command=fake_run) == "Z-05"


def test_classify_detail_code_returns_fallback_for_empty_work_text():
    def fake_run(cmd):
        raise AssertionError("run_command should not be called for empty text")

    assert classify_detail_code("", JOB_CODE_ANCILLARY, run_command=fake_run) == "Z-05"


def test_classify_detail_code_returns_empty_for_unknown_job_code():
    def fake_run(cmd):
        raise AssertionError("run_command should not be called for unknown job code")

    assert classify_detail_code("朝会", "9999999_未知", run_command=fake_run) == ""


def test_classify_detail_code_invokes_claude_with_haiku_model():
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="Z-05", stderr="")

    classify_detail_code("日報入力", JOB_CODE_ANCILLARY, run_command=fake_run)
    assert captured["cmd"][0] == "claude"
    assert captured["cmd"][1] == "-p"
    assert "--model" in captured["cmd"]
    assert "haiku" in captured["cmd"]


def test_classify_detail_code_accepts_lowercase_answer():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="z-99", stderr="")

    assert classify_detail_code("工数管理", JOB_CODE_ANCILLARY, run_command=fake_run) == "Z-99"


def test_detail_codes_cover_both_job_codes():
    assert set(DETAIL_CODES) == {JOB_CODE_ANCILLARY, JOB_CODE_COMMON}
    for candidates in DETAIL_CODES.values():
        assert candidates
        for code, label in candidates:
            assert code and label
