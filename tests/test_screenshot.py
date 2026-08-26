from datetime import datetime


def test_save_screenshot_writes_png_bytes_to_expected_path(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.screenshot import save_screenshot

    dt = datetime(2026, 8, 26, 9, 30, 0)
    path = save_screenshot(dt, lambda: b"fakepngdata")

    assert path.exists()
    assert path.read_bytes() == b"fakepngdata"
    assert path.name == "0930.png"


def test_save_screenshot_creates_parent_directory(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.screenshot import save_screenshot

    dt = datetime(2026, 8, 26, 10, 0, 0)
    path = save_screenshot(dt, lambda: b"data")

    assert path.parent.name == "screenshots"
