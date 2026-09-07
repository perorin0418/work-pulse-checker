from __future__ import annotations

from typing import Callable


class CountdownController:
    def __init__(self, total_seconds: int, on_tick: Callable[[int], None], on_finish: Callable[[], None]):
        self.total_seconds = total_seconds
        self.remaining = total_seconds
        self.on_tick = on_tick
        self.on_finish = on_finish
        self._finished = False

    def tick(self) -> None:
        if self._finished:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self.remaining = 0
            self._finished = True
            self.on_tick(self.remaining)
            self.on_finish()
        else:
            self.on_tick(self.remaining)

    def skip(self) -> None:
        if self._finished:
            return
        self.remaining = 0
        self._finished = True
        self.on_finish()

    @property
    def finished(self) -> bool:
        return self._finished


def run_countdown_window(total_seconds: int = 30) -> None:
    """予告カウントダウンを表示する。GUI依存のため自動テスト対象外(手動検証のみ)。"""
    import tkinter as tk

    from workpulse.theme import (
        COLOR_BORDER,
        COLOR_SURFACE,
        COLOR_TEXT,
        COLOR_WARN_ACCENT,
        COLOR_WARN_TEXT,
        FONT_LARGE_BOLD,
        FONT_NORMAL,
        apply_tk_scaling,
        enable_windows_dpi_awareness,
    )

    enable_windows_dpi_awareness()

    root = tk.Tk()
    apply_tk_scaling(root)
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.97)
    root.config(bg=COLOR_SURFACE, highlightbackground=COLOR_WARN_ACCENT, highlightthickness=2)

    frame = tk.Frame(root, bg=COLOR_SURFACE, padx=22, pady=16)
    frame.pack()

    accent_bar = tk.Frame(frame, bg=COLOR_WARN_ACCENT, height=3)
    accent_bar.pack(fill="x", pady=(0, 10))

    title_label = tk.Label(
        frame,
        text="まもなく作業内容の確認が表示されます",
        font=FONT_NORMAL,
        bg=COLOR_SURFACE,
        fg=COLOR_TEXT,
    )
    title_label.pack()

    seconds_label = tk.Label(frame, text="", font=FONT_LARGE_BOLD, bg=COLOR_SURFACE, fg=COLOR_WARN_TEXT)
    seconds_label.pack(pady=(4, 0))

    hint_label = tk.Label(
        frame,
        text="クリックでスキップ",
        font=("Yu Gothic UI", 8),
        bg=COLOR_SURFACE,
        fg=COLOR_BORDER,
    )
    hint_label.pack(pady=(6, 0))

    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    width = frame.winfo_reqwidth() + 8
    height = frame.winfo_reqheight() + 8
    x = screen_w - width - 20
    y = screen_h - height - 60
    root.geometry(f"{width}x{height}+{x}+{y}")

    def on_tick(remaining: int) -> None:
        seconds_label.config(text=f"残り {remaining} 秒")

    def on_finish() -> None:
        root.destroy()

    controller = CountdownController(total_seconds, on_tick, on_finish)
    on_tick(controller.remaining)

    def schedule_tick() -> None:
        if not controller.finished:
            controller.tick()
            if not controller.finished:
                root.after(1000, schedule_tick)

    root.after(1000, schedule_tick)
    for widget in (root, frame, title_label, seconds_label, hint_label, accent_bar):
        widget.bind("<Button-1>", lambda event: controller.skip())
    root.mainloop()
