from workpulse.activity import (
    ActiveWindowInfo,
    idle_seconds_from_ticks,
    read_active_window,
)


def test_idle_seconds_from_ticks_normal_case():
    assert idle_seconds_from_ticks(current_tick_ms=10_000, last_input_tick_ms=4_000) == 6


def test_idle_seconds_from_ticks_handles_wraparound():
    current = 1_000
    last_input = 2**32 - 3_000
    assert idle_seconds_from_ticks(current, last_input) == 4


def test_read_active_window_with_foreground_window():
    info = read_active_window(
        get_foreground_hwnd=lambda: 123,
        get_window_text=lambda hwnd: "Notepad",
        get_process_name_for_hwnd=lambda hwnd: "notepad.exe",
    )
    assert info == ActiveWindowInfo(window_title="Notepad", process_name="notepad.exe")


def test_read_active_window_without_foreground_window():
    info = read_active_window(
        get_foreground_hwnd=lambda: None,
        get_window_text=lambda hwnd: "should not be called",
        get_process_name_for_hwnd=lambda hwnd: "should not be called",
    )
    assert info == ActiveWindowInfo(window_title="", process_name="")
