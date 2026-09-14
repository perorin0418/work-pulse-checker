# src/workpulse/attendance/models.py
"""勤怠サービスに依存しない共通データ構造。

ここに定義する型はどのベンダーのサービス（HRMOS勤怠、ジョブカン等）でも
共通に使える語彙だけを持つ。ベンダー固有の項目は `extra` に逃がす。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class Credentials:
    """ログイン資格情報。"""

    login_id: str
    password: str
    # ベンダーによっては会社コード等が必要になるためここに入れる。
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkEntry:
    """1日ぶんの勤怠入力内容。

    time 系は「その日の時刻」を表す `datetime`（tz naive、ローカル時刻）とする。
    """

    work_date: date
    start_at: datetime | None = None
    end_at: datetime | None = None
    break_minutes: int | None = None
    note: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyRecord:
    """サービス側に登録済みの1日ぶんの勤怠実績。"""

    work_date: date
    start_at: datetime | None = None
    end_at: datetime | None = None
    break_minutes: int | None = None
    note: str = ""
    # 「承認済み」「申請中」などベンダー固有の状態を素の文字列で保持する。
    status: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SubmitResult:
    """打刻・勤怠登録の結果。"""

    work_date: date
    changed: bool
    message: str = ""


@dataclass(frozen=True)
class ReportRow:
    """日報1行ぶんの作業内容。

    `category` は画面上の大分類（「【共通】会議直接ＰＪ以外」など）。
    プロバイダーが表示名か ID かを解釈する。
    """

    category: str = ""
    service_name: str = ""
    plan_minutes: int | None = None
    result_minutes: int | None = None
    note: str = ""


@dataclass(frozen=True)
class DailyReport:
    """1日ぶんの日報（複数行）。"""

    work_date: date
    rows: list[ReportRow] = field(default_factory=list)
