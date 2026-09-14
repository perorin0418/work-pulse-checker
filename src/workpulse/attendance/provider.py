# src/workpulse/attendance/provider.py
"""勤怠サービスのラッパーインターフェース。

将来サービスが変わっても、このプロトコルを満たす実装を1つ追加して
設定を書き換えるだけで差し替えられるようにする。
"""
from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from workpulse.attendance.models import (
    Credentials,
    DailyReport,
    DailyRecord,
    SubmitResult,
    WorkEntry,
)


@runtime_checkable
class AttendanceProvider(Protocol):
    """勤怠サービス1つぶんの操作。

    実装は `with` で使えるようにする（`close()` でブラウザ等を解放）。
    失敗時は `workpulse.attendance.errors` の例外を送出する。
    """

    #: レジストリ・設定ファイルで使う識別子（例: "hrmos"）。
    name: str

    def login(self, credentials: Credentials) -> None:
        """ログインする。失敗時は AuthenticationError。"""
        ...

    def fetch_day(self, work_date: date) -> DailyRecord | None:
        """指定日の登録済み実績を返す。未登録なら None。"""
        ...

    def submit_day(self, entry: WorkEntry) -> SubmitResult:
        """指定日の勤怠を登録・更新する。"""
        ...

    def fetch_report(self, work_date: date) -> DailyReport:
        """指定日の日報を読み取る。"""
        ...

    def submit_report(self, report: DailyReport, replace: bool = True) -> SubmitResult:
        """指定日の日報を登録・更新する。

        `replace=True` なら既存行を置き換え、False なら追記する。
        """
        ...

    def close(self) -> None:
        """リソースを解放する。何度呼ばれても安全にする。"""
        ...


class BaseProvider:
    """`AttendanceProvider` の共通実装。

    コンテキストマネージャーと未対応操作のデフォルトを提供する。
    各プロバイダーはこれを継承して必要なメソッドだけ上書きすればよい。
    """

    name: str = "base"

    def __enter__(self) -> "BaseProvider":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        """既定では解放するものが無い。"""

    def login(self, credentials: Credentials) -> None:
        raise NotImplementedError

    def fetch_day(self, work_date: date) -> DailyRecord | None:
        from workpulse.attendance.errors import NotSupportedError

        raise NotSupportedError(f"{self.name} は実績取得に対応していない")

    def submit_day(self, entry: WorkEntry) -> SubmitResult:
        from workpulse.attendance.errors import NotSupportedError

        raise NotSupportedError(f"{self.name} は勤怠登録に対応していない")

    def fetch_report(self, work_date: date) -> DailyReport:
        from workpulse.attendance.errors import NotSupportedError

        raise NotSupportedError(f"{self.name} は日報取得に対応していない")

    def submit_report(self, report: DailyReport, replace: bool = True) -> SubmitResult:
        from workpulse.attendance.errors import NotSupportedError

        raise NotSupportedError(f"{self.name} は日報登録に対応していない")
