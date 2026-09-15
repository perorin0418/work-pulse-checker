# src/workpulse/attendance/__init__.py
"""勤怠サービスのラッパー層。

呼び出し側は `open_provider()` だけ使えばよく、どのサービスを使うかは
設定ファイル（`config/attendance.json`）で決まる。

    from workpulse.attendance import open_provider
    with open_provider() as provider:
        provider.submit_day(entry)
"""
from workpulse.attendance.config import AttendanceConfig, load_config
from workpulse.attendance.errors import (
    AttendanceError,
    AuthenticationError,
    NavigationError,
    NotSupportedError,
    SubmitError,
)
from workpulse.attendance.models import (
    Credentials,
    DailyRecord,
    DailyReport,
    ReportRow,
    SubmitResult,
    WorkEntry,
)
from workpulse.attendance.planner import PlanPolicy, PlanResult, WorkItem, plan_report
from workpulse.attendance.report_format import (
    build_note,
    parse_note,
    record_to_row,
    row_to_record,
    rows_from_records,
)
from workpulse.attendance.provider import AttendanceProvider, BaseProvider
from workpulse.attendance.service import open_provider

__all__ = [
    "AttendanceConfig",
    "AttendanceError",
    "AttendanceProvider",
    "AuthenticationError",
    "BaseProvider",
    "Credentials",
    "DailyRecord",
    "DailyReport",
    "NavigationError",
    "NotSupportedError",
    "PlanPolicy",
    "PlanResult",
    "ReportRow",
    "SubmitError",
    "SubmitResult",
    "WorkEntry",
    "WorkItem",
    "build_note",
    "load_config",
    "open_provider",
    "parse_note",
    "plan_report",
    "record_to_row",
    "row_to_record",
    "rows_from_records",
]
