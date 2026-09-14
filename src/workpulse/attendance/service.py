# src/workpulse/attendance/service.py
"""設定からプロバイダーを開くための入口。

呼び出し側がプロバイダー名やログイン手順を意識しなくて済むようにする。
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from workpulse.attendance import registry
from workpulse.attendance.config import AttendanceConfig, load_config
from workpulse.attendance.provider import AttendanceProvider


@contextmanager
def open_provider(
    config: AttendanceConfig | None = None,
    config_path: Path | None = None,
    login: bool = True,
) -> Iterator[AttendanceProvider]:
    """設定に従ってプロバイダーを生成し、ログインして返す。

    `with` を抜けると必ず `close()` する。
    """
    config = load_config(config_path) if config is None else config
    provider = registry.create(config.provider, **config.provider_kwargs())
    try:
        if login:
            provider.login(config.credentials())
        yield provider
    finally:
        provider.close()
