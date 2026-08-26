from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from workpulse.task_xml import build_task_xml, write_task_xml_file

MONITOR_TASK_NAME = "WorkPulseChecker_Monitor"
PROMPT_TASK_NAME = "WorkPulseChecker_Prompt"
DEFAULT_START_BOUNDARY = "2026-01-01T07:00:00"


def task_definitions(project_root: Path) -> list[dict]:
    return [
        {
            "name": MONITOR_TASK_NAME,
            "script_path": str(project_root / "monitor.py"),
            "repetition_interval": "PT1M",
        },
        {
            "name": PROMPT_TASK_NAME,
            "script_path": str(project_root / "prompt.py"),
            "repetition_interval": "PT30M",
        },
    ]


def install_task(
    task_name: str,
    script_path: str,
    repetition_interval: str,
    python_exe: str,
    project_root: Path,
    xml_dir: Path,
    run_command: Callable[[list[str]], subprocess.CompletedProcess],
) -> None:
    xml_body = build_task_xml(
        python_exe=python_exe,
        script_path=script_path,
        working_directory=str(project_root),
        start_boundary=DEFAULT_START_BOUNDARY,
        repetition_interval=repetition_interval,
    )
    xml_path = xml_dir / f"{task_name}.xml"
    write_task_xml_file(xml_body, xml_path)

    run_command(["schtasks", "/delete", "/tn", task_name, "/f"])
    result = run_command(["schtasks", "/create", "/tn", task_name, "/xml", str(xml_path), "/f"])
    if result.returncode != 0:
        raise RuntimeError(f"タスク登録に失敗しました: {task_name}\n{result.stderr}")


def install_all(project_root: Path, python_exe: str, run_command: Optional[Callable] = None) -> None:
    if run_command is None:
        def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True)

    xml_dir = project_root / "logs" / "task_xml"
    for task in task_definitions(project_root):
        install_task(
            task_name=task["name"],
            script_path=task["script_path"],
            repetition_interval=task["repetition_interval"],
            python_exe=python_exe,
            project_root=project_root,
            xml_dir=xml_dir,
            run_command=run_command,
        )


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent.parent
    python_exe = sys.executable
    install_all(project_root, python_exe)
    print("タスクスケジューラーへの登録が完了しました。")
