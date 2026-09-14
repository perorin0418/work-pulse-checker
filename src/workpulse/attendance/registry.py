# src/workpulse/attendance/registry.py
"""プロバイダーのレジストリ。

名前と「プロバイダーを作る関数」の対応表。サービスを追加するときは
`providers/` に実装を置き、`_BUILTIN` に1行足すだけでよい。
"""
from __future__ import annotations

from typing import Any, Callable

from workpulse.attendance.provider import AttendanceProvider

ProviderFactory = Callable[..., AttendanceProvider]

_registry: dict[str, ProviderFactory] = {}


def register(name: str, factory: ProviderFactory) -> None:
    """プロバイダーを登録する（同名は上書き）。"""
    _registry[name] = factory


def available() -> list[str]:
    """登録済みプロバイダー名を返す。"""
    _load_builtins()
    return sorted(_registry)


def create(name: str, **kwargs: Any) -> AttendanceProvider:
    """名前からプロバイダーを生成する。"""
    _load_builtins()
    try:
        factory = _registry[name]
    except KeyError:
        raise KeyError(
            f"未知の勤怠プロバイダー: {name!r}（利用可能: {', '.join(sorted(_registry))}）"
        ) from None
    return factory(**kwargs)


#: 組み込みプロバイダーの「名前 → import パス:クラス名」。
_BUILTIN = {
    "hrmos": "workpulse.attendance.providers.hrmos:HrmosProvider",
}

_loaded = False


def _load_builtins() -> None:
    """組み込みプロバイダーを遅延登録する。

    Playwright 等の重い依存を、実際に使うときまで import しないための遅延化。
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    from importlib import import_module

    for name, target in _BUILTIN.items():
        if name in _registry:
            continue
        module_path, _, attr = target.partition(":")

        def factory(_module_path: str = module_path, _attr: str = attr, **kwargs: Any):
            cls = getattr(import_module(_module_path), _attr)
            return cls(**kwargs)

        _registry[name] = factory
