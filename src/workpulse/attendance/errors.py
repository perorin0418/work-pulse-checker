# src/workpulse/attendance/errors.py
"""勤怠サービス操作の共通例外。

呼び出し側がベンダー固有の例外（Playwright の TimeoutError 等）を
知らずに済むよう、プロバイダー実装はここの例外に変換して送出する。
"""
from __future__ import annotations


class AttendanceError(Exception):
    """勤怠サービス操作の基底例外。"""


class AuthenticationError(AttendanceError):
    """ログインに失敗した（ID・パスワード誤り、ロック等）。"""


class NavigationError(AttendanceError):
    """目的の画面に到達できなかった（URL変更、要素が見つからない等）。"""


class SubmitError(AttendanceError):
    """勤怠の登録・更新に失敗した。"""


class NotSupportedError(AttendanceError):
    """そのプロバイダーが当該操作に対応していない。"""
