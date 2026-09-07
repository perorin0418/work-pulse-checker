from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from workpulse.paths import screenshot_path


def save_screenshot(dt: datetime, capture_png_bytes: Callable[[], bytes]) -> Path:
    path = screenshot_path(dt)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(capture_png_bytes())
    return path


def try_save_screenshot(dt: datetime, capture_png_bytes: Callable[[], bytes]) -> Optional[Path]:
    """撮影・保存に失敗しても例外を外へ伝播させず None を返す。

    ロック画面中は Windows の GDI (`BitBlt`) がキャプチャに失敗することがある。
    このスロットのスクリーンショットが撮れないだけで、確認ダイアログ自体は
    継続表示できるべきなので、呼び出し元をクラッシュさせない。
    """
    try:
        return save_screenshot(dt, capture_png_bytes)
    except Exception:
        return None


def capture_png_bytes_mss() -> bytes:
    import mss
    import mss.tools

    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)
        return mss.tools.to_png(shot.rgb, shot.size)
