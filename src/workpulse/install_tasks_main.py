from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from workpulse.schedule import DEFAULT_START_BOUNDARY
from workpulse.task_xml import build_task_xml, write_task_xml_file

MONITOR_TASK_NAME = "WorkPulseChecker_Monitor"
PROMPT_TASK_NAME = "WorkPulseChecker_Prompt"


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


def resolve_uv_executable(which: Callable[[str], Optional[str]] = shutil.which) -> str:
    """コンソールを開かずに実行できる `uvw.exe` があればそちらを使う。

    タスクスケジューラーが `uv.exe`（コンソールサブシステム）を起動すると
    実行のたびにコマンドプロンプトの黒いウィンドウが一瞬表示される。同じ
    `uv` に同梱される `uvw.exe`（GUIサブシステム、標準入出力を持たない）が
    PATH上にあれば、それに差し替えることでサイレント実行にできる。
    見つからない場合は `uv.exe` にフォールバックする（コンソールが開く
    挙動を維持しつつ、実行不能にはしない）。
    """
    uvw_path = which("uvw")
    if uvw_path:
        return uvw_path
    uv_path = which("uv")
    if uv_path:
        return uv_path
    raise RuntimeError("uv（または uvw）が見つかりません。PATHにuvをインストールしてください。")


def build_uv_run_arguments(project_root: Path, script_path: str) -> str:
    """`uv run --project <root> python "<script>"` の引数文字列を組み立てる。"""
    return f'run --project "{project_root}" python "{script_path}"'


def install_task(
    task_name: str,
    script_path: str,
    repetition_interval: str,
    command: str,
    project_root: Path,
    xml_dir: Path,
    run_command: Callable[[list[str]], subprocess.CompletedProcess],
) -> None:
    xml_body = build_task_xml(
        command=command,
        arguments=build_uv_run_arguments(project_root, script_path),
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


def install_all(
    project_root: Path,
    command: str,
    run_command: Optional[Callable] = None,
) -> None:
    if run_command is None:
        def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True)

    xml_dir = project_root / "logs" / "task_xml"
    for task in task_definitions(project_root):
        install_task(
            task_name=task["name"],
            script_path=task["script_path"],
            repetition_interval=task["repetition_interval"],
            command=command,
            project_root=project_root,
            xml_dir=xml_dir,
            run_command=run_command,
        )


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent.parent
    command = resolve_uv_executable()
    install_all(project_root, command)
    print("タスクスケジューラーへの登録が完了しました。")


if __name__ == "__main__":
    main()
