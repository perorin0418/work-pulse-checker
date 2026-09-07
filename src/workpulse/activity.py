from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

TICK_COUNT_WRAP = 2**32


def idle_seconds_from_ticks(current_tick_ms: int, last_input_tick_ms: int) -> int:
    """GetTickCount は約49.7日で0にラップアラウンドするため、負数になった場合は補正する。"""
    delta_ms = current_tick_ms - last_input_tick_ms
    if delta_ms < 0:
        delta_ms += TICK_COUNT_WRAP
    return delta_ms // 1000


@dataclass
class ActiveWindowInfo:
    window_title: str
    process_name: str


def read_active_window(
    get_foreground_hwnd: Callable[[], Optional[int]],
    get_window_text: Callable[[int], str],
    get_process_name_for_hwnd: Callable[[int], str],
) -> ActiveWindowInfo:
    hwnd = get_foreground_hwnd()
    if hwnd is None:
        return ActiveWindowInfo(window_title="", process_name="")
    title = get_window_text(hwnd) or ""
    process_name = get_process_name_for_hwnd(hwnd) or ""
    return ActiveWindowInfo(window_title=title, process_name=process_name)


def win32_get_foreground_hwnd() -> Optional[int]:
    import win32gui

    hwnd = win32gui.GetForegroundWindow()
    return hwnd if hwnd else None


def win32_get_window_text(hwnd: int) -> str:
    import win32gui

    return win32gui.GetWindowText(hwnd)


def win32_get_process_name_for_hwnd(hwnd: int) -> str:
    import win32process
    import psutil

    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    try:
        return psutil.Process(pid).name()
    except Exception:
        return ""


def get_idle_seconds() -> int:
    import win32api

    current_tick = win32api.GetTickCount()
    last_input_tick = win32api.GetLastInputInfo()
    return idle_seconds_from_ticks(current_tick, last_input_tick)
