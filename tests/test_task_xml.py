import xml.etree.ElementTree as ET

from workpulse.task_xml import build_task_xml, write_task_xml_file

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _build_sample_xml() -> str:
    return build_task_xml(
        python_exe="C:\\venv\\Scripts\\python.exe",
        script_path="C:\\work-pulse-checker\\rebuild\\monitor.py",
        working_directory="C:\\work-pulse-checker\\rebuild",
        start_boundary="2026-01-01T07:00:00",
        repetition_interval="PT1M",
    )


def test_build_task_xml_sets_start_boundary_and_repetition():
    root = ET.fromstring(_build_sample_xml())
    trigger = root.find(".//t:CalendarTrigger", NS)
    assert trigger.find("t:StartBoundary", NS).text == "2026-01-01T07:00:00"
    assert trigger.find("t:Repetition/t:Interval", NS).text == "PT1M"
    assert trigger.find("t:Repetition/t:Duration", NS).text == "PT15H"


def test_build_task_xml_restricts_to_weekdays():
    root = ET.fromstring(_build_sample_xml())
    days = root.findall(".//t:ScheduleByWeek/t:DaysOfWeek/*", NS)
    day_tags = [d.tag.rsplit("}", 1)[-1] for d in days]
    assert day_tags == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def test_build_task_xml_prevents_multiple_instances():
    root = ET.fromstring(_build_sample_xml())
    policy = root.find("t:Settings/t:MultipleInstancesPolicy", NS)
    assert policy.text == "IgnoreNew"


def test_build_task_xml_sets_action_command():
    root = ET.fromstring(_build_sample_xml())
    exec_node = root.find("t:Actions/t:Exec", NS)
    assert exec_node.find("t:Command", NS).text == "C:\\venv\\Scripts\\python.exe"
    assert "monitor.py" in exec_node.find("t:Arguments", NS).text
    assert exec_node.find("t:WorkingDirectory", NS).text == "C:\\work-pulse-checker\\rebuild"


def test_write_task_xml_file_writes_utf16_with_declaration(tmp_path):
    xml_body = _build_sample_xml()
    path = tmp_path / "task.xml"
    write_task_xml_file(xml_body, path)

    content = path.read_text(encoding="utf-16")
    assert content.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    assert "<Task" in content
