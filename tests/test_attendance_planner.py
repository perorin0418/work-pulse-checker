# tests/test_attendance_planner.py
"""勤怠実績から日報を組み立てる判定ロジックのテスト。"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from workpulse.attendance.models import DailyRecord
from workpulse.attendance.planner import (
    PlanPolicy,
    WorkItem,
    is_holiday,
    plan_report,
    work_minutes_of,
)

DAY = date(2026, 9, 11)


def record(**kwargs) -> DailyRecord:
    extra = {"actual_time": "3:36", "total_time": "7:36"}
    extra.update(kwargs.pop("extra", {}))
    base = dict(work_date=DAY, status="出勤", note="", extra=extra)
    base.update(kwargs)
    return DailyRecord(**base)


def test_skips_when_record_missing():
    result = plan_report(None)
    assert result.skipped is True
    assert result.report.rows == []


@pytest.mark.parametrize("status", ["休日", "日曜(法定休日)", "全休", "欠勤"])
def test_skips_holidays(status):
    result = plan_report(record(status=status))
    assert result.skipped is True
    assert "休" in result.reason or "欠勤" in result.reason


def test_half_day_leave_is_not_skipped():
    # 有休(PM) は半休なので午前中の実労働ぶんの日報が要る。
    result = plan_report(record(status="有休(PM)"))
    assert result.skipped is False
    assert result.work_minutes == 216


def test_skips_when_no_work_time():
    result = plan_report(record(extra={"actual_time": "0:00"}))
    assert result.skipped is True
    assert "0" in result.reason


def test_default_single_row():
    policy = PlanPolicy(default_category="【共通】休暇", default_service_name="通常業務")
    result = plan_report(record(), policy=policy)

    assert len(result.report.rows) == 1
    row = result.report.rows[0]
    assert row.category == "【共通】休暇"
    assert row.service_name == "通常業務"
    assert row.result_minutes == 216


def test_distributes_across_items():
    items = [WorkItem(service_name="A"), WorkItem(service_name="B")]
    result = plan_report(record(), items=items)

    assert [r.result_minutes for r in result.report.rows] == [108, 108]
    assert sum(r.result_minutes for r in result.report.rows) == 216


def test_distribution_absorbs_remainder_in_last_row():
    items = [WorkItem(service_name="A"), WorkItem(service_name="B"), WorkItem(service_name="C")]
    result = plan_report(record(), items=items)

    minutes = [r.result_minutes for r in result.report.rows]
    assert sum(minutes) == 216
    assert minutes == [72, 72, 72]


def test_fixed_minutes_are_respected():
    items = [WorkItem(service_name="会議", minutes=30), WorkItem(service_name="開発")]
    result = plan_report(record(), items=items)

    assert [r.result_minutes for r in result.report.rows] == [30, 186]


def test_warns_when_fixed_exceeds_actual():
    items = [WorkItem(service_name="会議", minutes=600)]
    result = plan_report(record(), items=items)

    assert result.warnings
    assert "超えている" in result.warnings[0]


def test_uses_total_time_when_policy_says_so():
    result = plan_report(record(), policy=PlanPolicy(minutes_source="total_time"))
    assert result.work_minutes == 456  # 7:36


def test_falls_back_to_punch_difference():
    rec = DailyRecord(
        work_date=DAY,
        start_at=datetime(2026, 9, 11, 9, 0),
        end_at=datetime(2026, 9, 11, 18, 0),
        break_minutes=60,
        status="出勤",
        extra={},
    )
    assert work_minutes_of(rec) == 480


def test_inherit_note_option():
    rec = record(note="通院してきます")
    assert plan_report(rec).report.rows[0].note == ""
    assert plan_report(rec, policy=PlanPolicy(inherit_note=True)).report.rows[0].note == "通院してきます"


def test_item_note_wins_over_inherited():
    rec = record(note="勤怠備考")
    items = [WorkItem(service_name="A", note="作業備考")]
    result = plan_report(rec, items=items, policy=PlanPolicy(inherit_note=True))
    assert result.report.rows[0].note == "作業備考"


def test_is_holiday_helper():
    assert is_holiday(record(status="土祝日(法定外休日)")) is True
    assert is_holiday(record(status="出勤")) is False
