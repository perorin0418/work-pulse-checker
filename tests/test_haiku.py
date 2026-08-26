import subprocess
from pathlib import Path

from workpulse.haiku import build_prompt_text, predict_work_content


def test_build_prompt_text_includes_summary_and_screenshot_path():
    text = build_prompt_text("要約テキスト", Path("data/2026/08/26/screenshots/0930.png"))
    assert "要約テキスト" in text
    assert "0930.png" in text


def test_predict_work_content_returns_trimmed_stdout_on_success():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="資料作成\n", stderr="")

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == "資料作成"


def test_predict_work_content_returns_empty_on_nonzero_exit():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == ""


def test_predict_work_content_returns_empty_on_exception():
    def fake_run(cmd):
        raise FileNotFoundError("claude command not found")

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == ""


def test_predict_work_content_invokes_claude_with_haiku_model():
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert captured["cmd"][0] == "claude"
    assert captured["cmd"][1] == "-p"
    assert "--model" in captured["cmd"]
    assert "haiku" in captured["cmd"]
