import subprocess

import pytest

from workpulse.install_tasks_main import (
    MONITOR_TASK_NAME,
    PROMPT_TASK_NAME,
    install_all,
    install_task,
)


def _ok(cmd):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


def test_install_all_registers_monitor_and_prompt_tasks(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _ok(cmd)

    install_all(tmp_path, python_exe="C:\\venv\\Scripts\\python.exe", run_command=fake_run)

    create_calls = [c for c in calls if "/create" in c]
    assert len(create_calls) == 2
    task_names = [c[c.index("/tn") + 1] for c in create_calls]
    assert MONITOR_TASK_NAME in task_names
    assert PROMPT_TASK_NAME in task_names


def test_install_all_deletes_existing_task_before_creating(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _ok(cmd)

    install_all(tmp_path, python_exe="C:\\venv\\Scripts\\python.exe", run_command=fake_run)

    delete_calls = [c for c in calls if "/delete" in c]
    assert len(delete_calls) == 2


def test_install_all_writes_xml_files(tmp_path):
    def fake_run(cmd):
        return _ok(cmd)

    install_all(tmp_path, python_exe="C:\\venv\\Scripts\\python.exe", run_command=fake_run)

    xml_dir = tmp_path / "logs" / "task_xml"
    assert (xml_dir / f"{MONITOR_TASK_NAME}.xml").exists()
    assert (xml_dir / f"{PROMPT_TASK_NAME}.xml").exists()


def test_install_task_raises_when_create_fails(tmp_path):
    def fake_run(cmd):
        if "/create" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="denied")
        return _ok(cmd)

    with pytest.raises(RuntimeError):
        install_task(
            task_name="SomeTask",
            script_path=str(tmp_path / "monitor.py"),
            repetition_interval="PT1M",
            python_exe="C:\\venv\\Scripts\\python.exe",
            project_root=tmp_path,
            xml_dir=tmp_path / "logs" / "task_xml",
            run_command=fake_run,
        )
