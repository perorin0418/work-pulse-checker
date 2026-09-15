import subprocess

import pytest

from workpulse.install_tasks_main import (
    MONITOR_TASK_NAME,
    PROMPT_TASK_NAME,
    build_uv_run_arguments,
    install_all,
    install_task,
    resolve_uv_executable,
)


def _ok(cmd):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


def test_install_all_registers_monitor_and_prompt_tasks(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _ok(cmd)

    install_all(tmp_path, command="C:\\uv\\uvw.exe", run_command=fake_run)

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

    install_all(tmp_path, command="C:\\uv\\uvw.exe", run_command=fake_run)

    delete_calls = [c for c in calls if "/delete" in c]
    assert len(delete_calls) == 2


def test_install_all_writes_xml_files(tmp_path):
    def fake_run(cmd):
        return _ok(cmd)

    install_all(tmp_path, command="C:\\uv\\uvw.exe", run_command=fake_run)

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
            command="C:\\uv\\uvw.exe",
            project_root=tmp_path,
            xml_dir=tmp_path / "logs" / "task_xml",
            run_command=fake_run,
        )


def test_resolve_uv_executable_prefers_uvw(tmp_path):
    def fake_which(name):
        return {"uvw": "C:\\uv\\uvw.exe", "uv": "C:\\uv\\uv.exe"}.get(name)

    result = resolve_uv_executable(which=fake_which)

    assert result == "C:\\uv\\uvw.exe"


def test_resolve_uv_executable_falls_back_to_uv_when_uvw_missing():
    def fake_which(name):
        return {"uv": "C:\\uv\\uv.exe"}.get(name)

    result = resolve_uv_executable(which=fake_which)

    assert result == "C:\\uv\\uv.exe"


def test_resolve_uv_executable_raises_when_neither_found():
    def fake_which(name):
        return None

    with pytest.raises(RuntimeError):
        resolve_uv_executable(which=fake_which)


def test_build_uv_run_arguments_quotes_project_and_script(tmp_path):
    script_path = str(tmp_path / "monitor.py")

    result = build_uv_run_arguments(tmp_path, script_path)

    assert result == f'run --project "{tmp_path}" python "{script_path}"'


def test_install_all_uses_uv_run_arguments_in_task_xml(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _ok(cmd)

    install_all(tmp_path, command="C:\\uv\\uvw.exe", run_command=fake_run)

    xml_dir = tmp_path / "logs" / "task_xml"
    xml_content = (xml_dir / f"{MONITOR_TASK_NAME}.xml").read_text(encoding="utf-16")
    assert "C:\\uv\\uvw.exe" in xml_content
    assert "monitor.py" in xml_content
    assert "run --project" in xml_content
