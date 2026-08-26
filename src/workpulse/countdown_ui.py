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

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    label = tk.Label(root, text="", font=("Yu Gothic UI", 14), padx=16, pady=12)
    label.pack()

    root.update_idletasks()
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    width = label.winfo_reqwidth() + 32
    height = label.winfo_reqheight() + 24
    x = screen_w - width - 20
    y = screen_h - height - 60
    root.geometry(f"{width}x{height}+{x}+{y}")

    def on_tick(remaining: int) -> None:
        label.config(text=f"まもなく作業内容の確認が表示されます\n残り{remaining}秒")

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
    root.bind("<Button-1>", lambda event: controller.skip())
    root.mainloop()
