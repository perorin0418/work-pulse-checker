from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

from workpulse.paths import screenshot_path


def save_screenshot(dt: datetime, capture_png_bytes: Callable[[], bytes]) -> Path:
    path = screenshot_path(dt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png_bytes())
    return path


def capture_png_bytes_mss() -> bytes:
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        return mss.tools.to_png(shot.rgb, shot.size)
