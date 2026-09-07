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


def test_try_save_screenshot_returns_path_on_success(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.screenshot import try_save_screenshot

    dt = datetime(2026, 8, 26, 9, 30, 0)
    path = try_save_screenshot(dt, lambda: b"data")

    assert path is not None
    assert path.exists()


def test_try_save_screenshot_returns_none_on_capture_failure(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.screenshot import try_save_screenshot

    def failing_capture():
        raise RuntimeError("Windows graphics function failed: BitBlt")

    dt = datetime(2026, 8, 26, 9, 30, 0)
    path = try_save_screenshot(dt, failing_capture)

    assert path is None
