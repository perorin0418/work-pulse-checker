# src/workpulse/attendance/planner.py
"""勤怠実績から日報の行を組み立てる判定ロジック。

勤怠サービスに依存しない。`DailyRecord`（サービスから読んだ実績）と
任意の作業内容を入力に取り、`DailyReport`（登録する日報）を返す。

判定の方針:

- 休日・全休の日は日報を作らない（行なし）
- 実労働時間が 0 の日も作らない
- 作業内容が無ければ既定の1行にまとめる
- 作業内容がある場合は、その比率で実労働時間を按分する
  （合計が実労働時間に一致するよう、最後の行で端数を吸収する）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from workpulse.attendance.models import DailyRecord, DailyReport, ReportRow

#: 勤務区分に含まれていたら「日報不要」とみなす語。
HOLIDAY_KEYWORDS = ("休日", "全休", "欠勤")

#: 実労働時間が取れなかったときに使う既定値（分）。
DEFAULT_WORK_MINUTES = 0


@dataclass(frozen=True)
class WorkItem:
    """日報に載せたい作業1件。

    `minutes` が指定されていればその時間を使い、無ければ実労働時間を
    件数で按分する。
    """

    service_name: str
    category: str = ""
    minutes: int | None = None
    note: str = ""


@dataclass(frozen=True)
class PlanPolicy:
    """日報を組み立てるときの既定値。"""

    #: 作業内容が無いときに使う大分類と業務名。
    default_category: str = ""
    default_service_name: str = "通常業務"
    #: 実労働時間ではなく総労働時間を基準にする場合は "total_time"。
    minutes_source: str = "actual_time"
    #: 備考に勤怠側の備考を引き継ぐか。
    inherit_note: bool = False


@dataclass(frozen=True)
class PlanResult:
    """判定の結果。なぜそうなったかを `reason` に残す。"""

    report: DailyReport
    reason: str
    work_minutes: int = 0
    skipped: bool = False
    warnings: list[str] = field(default_factory=list)


def plan_report(
    record: DailyRecord | None,
    items: list[WorkItem] | None = None,
    policy: PlanPolicy | None = None,
) -> PlanResult:
    """勤怠実績と作業内容から、登録すべき日報を決める。"""
    policy = policy or PlanPolicy()
    items = list(items or [])

    if record is None:
        return PlanResult(
            report=DailyReport(work_date=_missing_date(), rows=[]),
            reason="勤怠実績が取得できない",
            skipped=True,
        )

    if is_holiday(record):
        return PlanResult(
            report=DailyReport(work_date=record.work_date, rows=[]),
            reason=f"勤務区分が休みのため日報不要（{record.status or '区分不明'}）",
            skipped=True,
        )

    work_minutes = work_minutes_of(record, policy)
    if work_minutes <= 0:
        return PlanResult(
            report=DailyReport(work_date=record.work_date, rows=[]),
            reason="実労働時間が0のため日報不要",
            skipped=True,
        )

    note = record.note if policy.inherit_note else ""

    if not items:
        rows = [
            ReportRow(
                category=policy.default_category,
                service_name=policy.default_service_name,
                result_minutes=work_minutes,
                note=note,
            )
        ]
        reason = f"作業内容の指定が無いため既定の1行に{_hhmm(work_minutes)}を計上"
        return PlanResult(
            report=DailyReport(work_date=record.work_date, rows=rows),
            reason=reason,
            work_minutes=work_minutes,
        )

    rows, warnings = _distribute(items, work_minutes, policy, note)
    reason = f"{len(rows)}件の作業に実労働時間{_hhmm(work_minutes)}を配分"
    return PlanResult(
        report=DailyReport(work_date=record.work_date, rows=rows),
        reason=reason,
        work_minutes=work_minutes,
        warnings=warnings,
    )


def is_holiday(record: DailyRecord) -> bool:
    """勤務区分から「日報が要らない日」かを判定する。"""
    status = record.status or ""
    return any(word in status for word in HOLIDAY_KEYWORDS)


def work_minutes_of(record: DailyRecord, policy: PlanPolicy | None = None) -> int:
    """その日の労働時間（分）を求める。

    サービスが返した実労働時間を優先し、無ければ打刻の差から計算する。
    """
    policy = policy or PlanPolicy()
    text = str(record.extra.get(policy.minutes_source, "") or "")
    minutes = _hhmm_to_minutes(text)
    if minutes is not None:
        return minutes

    if record.start_at is not None and record.end_at is not None:
        delta = int((record.end_at - record.start_at).total_seconds() // 60)
        return max(delta - (record.break_minutes or 0), 0)

    return DEFAULT_WORK_MINUTES


def _distribute(
    items: list[WorkItem],
    total_minutes: int,
    policy: PlanPolicy,
    note: str,
) -> tuple[list[ReportRow], list[str]]:
    """作業一覧に労働時間を配分して行を作る。"""
    warnings: list[str] = []
    fixed = sum(i.minutes for i in items if i.minutes is not None)
    floating = [i for i in items if i.minutes is None]

    if fixed > total_minutes:
        warnings.append(
            f"指定時間の合計{_hhmm(fixed)}が実労働時間{_hhmm(total_minutes)}を超えている"
        )

    remainder = max(total_minutes - fixed, 0)
    share = remainder // len(floating) if floating else 0

    rows: list[ReportRow] = []
    for item in items:
        minutes = item.minutes if item.minutes is not None else share
        rows.append(
            ReportRow(
                category=item.category or policy.default_category,
                service_name=item.service_name,
                result_minutes=minutes,
                note=item.note or note,
            )
        )

    # 端数は最後の按分対象に寄せて、合計を実労働時間に一致させる。
    if floating:
        gap = total_minutes - sum(r.result_minutes or 0 for r in rows)
        if gap:
            last = max(i for i, item in enumerate(items) if item.minutes is None)
            rows[last] = ReportRow(
                category=rows[last].category,
                service_name=rows[last].service_name,
                result_minutes=(rows[last].result_minutes or 0) + gap,
                note=rows[last].note,
            )

    return rows, warnings


def _hhmm_to_minutes(text: str) -> int | None:
    """"3:36" を分にする。解釈できなければ None。"""
    text = (text or "").strip()
    if ":" not in text:
        return None
    hours, _, minutes = text.partition(":")
    try:
        return int(hours) * 60 + int(minutes)
    except ValueError:
        return None


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _missing_date():
    from datetime import date

    return date.min
