import subprocess

from workpulse.job_code import (
    JOB_CODE_ANCILLARY,
    JOB_CODE_COMMON,
    build_classification_prompt,
    classify_job_code,
)


def test_build_classification_prompt_includes_work_text_and_categories():
    text = build_classification_prompt("朝会")
    assert "朝会" in text
    assert "課会" in text
    assert "1on1ミーティング" in text


def test_classify_job_code_returns_ancillary_when_haiku_answers_yes():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="yes\n", stderr="")

    result = classify_job_code("朝会", run_command=fake_run)
    assert result == JOB_CODE_ANCILLARY


def test_classify_job_code_returns_common_when_haiku_answers_no():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="no\n", stderr="")

    result = classify_job_code("資料作成", run_command=fake_run)
    assert result == JOB_CODE_COMMON


def test_classify_job_code_falls_back_to_common_on_nonzero_exit():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

    result = classify_job_code("朝会", run_command=fake_run)
    assert result == JOB_CODE_COMMON


def test_classify_job_code_falls_back_to_common_on_exception():
    def fake_run(cmd):
        raise FileNotFoundError("claude command not found")

    result = classify_job_code("朝会", run_command=fake_run)
    assert result == JOB_CODE_COMMON


def test_classify_job_code_falls_back_to_common_when_stdout_is_none():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=None, stderr=None)

    result = classify_job_code("朝会", run_command=fake_run)
    assert result == JOB_CODE_COMMON


def test_classify_job_code_returns_common_for_empty_work_text():
    def fake_run(cmd):
        raise AssertionError("run_command should not be called for empty text")

    result = classify_job_code("", run_command=fake_run)
    assert result == JOB_CODE_COMMON


def test_classify_job_code_invokes_claude_with_haiku_model():
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="no", stderr="")

    classify_job_code("資料作成", run_command=fake_run)
    assert captured["cmd"][0] == "claude"
    assert captured["cmd"][1] == "-p"
    assert "--model" in captured["cmd"]
    assert "haiku" in captured["cmd"]


def test_classify_job_code_treats_answer_case_insensitively():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="YES", stderr="")

    result = classify_job_code("課会", run_command=fake_run)
    assert result == JOB_CODE_ANCILLARY
