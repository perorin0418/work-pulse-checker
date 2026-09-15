from __future__ import annotations

from pathlib import Path

from workpulse.schedule import DEFAULT_REPETITION_DURATION

TASK_XML_TEMPLATE = """<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
      <Repetition>
        <Interval>{repetition_interval}</Interval>
        <Duration>{repetition_duration}</Duration>
        <StopAtDurationEnd>true</StopAtDurationEnd>
      </Repetition>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{command}</Command>
      <Arguments>{arguments}</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""


def build_task_xml(
    command: str,
    arguments: str,
    working_directory: str,
    start_boundary: str,
    repetition_interval: str,
    repetition_duration: str = DEFAULT_REPETITION_DURATION,
) -> str:
    """タスクスケジューラー登録用のXMLを組み立てる。

    `command` は実行ファイル（例: `uvw.exe` のフルパス）、`arguments` は
    そのコマンドに渡す引数をそのまま文字列で渡す（呼び出し側で必要な
    クオートを済ませておくこと。例: `run --project "C:\\proj" python "monitor.py"`）。
    """
    return TASK_XML_TEMPLATE.format(
        command=command,
        arguments=arguments,
        working_directory=working_directory,
        start_boundary=start_boundary,
        repetition_interval=repetition_interval,
        repetition_duration=repetition_duration,
    )


def write_task_xml_file(xml_body: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = '<?xml version="1.0" encoding="UTF-16"?>\n' + xml_body
    path.write_text(content, encoding="utf-16")
