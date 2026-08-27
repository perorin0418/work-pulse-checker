import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from workpulse.haiku import build_prompt_text, predict_work_content


def test_build_prompt_text_includes_summary_and_screenshot_path():
    text = build_prompt_text("要約テキスト", Path("data/2026/08/26/screenshots/0930.png"))
    assert "要約テキスト" in text
    assert "0930.png" in text


def test_build_prompt_text_includes_today_history_when_provided():
    text = build_prompt_text(
        "要約テキスト",
        Path("shot.png"),
        today_history=["資料作成", "レビュー対応"],
    )
    assert "資料作成" in text
    assert "レビュー対応" in text
    assert "本日" in text


def test_build_prompt_text_omits_history_section_when_empty():
    text = build_prompt_text("要約テキスト", Path("shot.png"), today_history=[])
    assert "本日" not in text


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


def test_predict_work_content_includes_today_history_in_prompt():
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    predict_work_content(
        "要約", Path("shot.png"), run_command=fake_run, today_history=["資料作成"]
    )
    assert "資料作成" in captured["cmd"][2]


def test_predict_work_content_returns_empty_when_stdout_is_none():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=None, stderr=None)

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == ""


def test_predict_work_content_default_run_command_suppresses_console_window_on_windows():
    captured_kwargs = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    with patch("workpulse.haiku.subprocess.run", side_effect=fake_subprocess_run):
        predict_work_content("要約", Path("shot.png"))

    if sys.platform == "win32":
        assert captured_kwargs.get("creationflags", 0) & subprocess.CREATE_NO_WINDOW
    else:
        assert "creationflags" not in captured_kwargs


def test_predict_work_content_default_run_command_redirects_stdin_from_devnull():
    captured_kwargs = {}

    def fake_subprocess_run(cmd, **kwargs):
        captured_kwargs.update(kwargs)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    with patch("workpulse.haiku.subprocess.run", side_effect=fake_subprocess_run):
        predict_work_content("要約", Path("shot.png"))

    assert captured_kwargs.get("stdin") == subprocess.DEVNULL
