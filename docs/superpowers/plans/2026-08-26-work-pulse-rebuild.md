# 作業監視・記録アプリ ゼロベース再構築 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Windowsタスクスケジューラーに駆動される短命Pythonプロセス群（1分間隔の操作監視、30分間隔の作業内容確認プロンプト）と、記録データの閲覧・編集CLI、タスク登録スクリプトを構築する。常駐プロセスは持たない。

**Architecture:** `src/workpulse/` にOSアクセス（win32・tkinter・subprocess・スクリーンショット）を薄くラップした関数群と、それらを組み合わせる純粋なロジック関数を分離して配置する。各エントリスクリプト（`monitor.py` / `prompt.py` / `view.py` / `install_tasks.py`）はリポジトリ直下に置き、`src/workpulse/*_main.py` の `main()` を呼ぶだけの薄いラッパーとする。日次データは `data/YYYY/MM/DD/` 配下にParquet形式で保存する。

**Tech Stack:** Python 3.11+, pandas, pyarrow, mss（スクリーンショット）, pywin32 + psutil（Win32 API）, tkinter（GUI, 標準ライブラリ）, pytest（テスト）

## Global Constraints

- 常駐プロセスを持たない。すべてタスクスケジューラーが起動する短命プロセスとして実装する
- データ配置は `data/YYYY/MM/DD/audit.parquet` と `data/YYYY/MM/DD/work-content.parquet`、スクリーンショットは `data/YYYY/MM/DD/screenshots/HHMM.png`
- `audit.parquet` の列は `timestamp`, `foreground_window_title`, `foreground_process_name`, `idle_seconds` の4列のみ
- `work-content.parquet` の列は `slot_start`, `slot_end`, `predicted_text`, `confirmed_text`, `status`, `screenshot_path` の6列のみ。`status` は `confirmed` または `auto_confirmed`
- タスクの多重起動防止はタスクスケジューラーの `MultipleInstancesPolicy=IgnoreNew` に一任し、アプリ側でロックファイル等は実装しない
- タスクは平日（月〜金）7:00〜22:00のみ起動するようにタスク定義で制限する
- フルスクリーンアプリ検出による表示抑制は実装しない
- `view.py` は `work-content.parquet` の `confirmed_text` のみ編集可能。`audit.parquet` は閲覧・編集どちらも対象外
- 確認ダイアログはタイムアウト（既定300秒）で自動確定し、`status` を `auto_confirmed` にする。ユーザーが確定した場合は `confirmed`
- `claude -p` 呼び出し失敗時は `predicted_text` を空文字とし、フローを継続する（致命的エラーにしない）
- 各エントリプロセスの想定外例外は `logs/<component>_error.log` に記録し、非0終了する

---

### Task 1: プロジェクト雛形（依存関係・パッケージ骨格・pytest設定）

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.gitignore`
- Create: `conftest.py`
- Create: `src/workpulse/__init__.py`
- Test: `tests/test_scaffolding.py`

**Interfaces:**
- Produces: `workpulse` パッケージが `src/workpulse/` 配下にインポート可能な状態で存在する。`conftest.py` が `src/` を `sys.path` に追加するため、以降のすべてのテストは `from workpulse.xxx import yyy` で参照できる

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_scaffolding.py
def test_workpulse_package_is_importable():
    import workpulse  # noqa: F401
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_scaffolding.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse'`)

- [ ] **Step 3: 雛形ファイルを作成する**

```text
# requirements.txt
pandas
pyarrow
mss
pywin32
psutil
```

```text
# requirements-dev.txt
-r requirements.txt
pytest
```

```gitignore
# .gitignore
data/
logs/
__pycache__/
*.pyc
.venv/
venv/
```

```python
# conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))
```

```python
# src/workpulse/__init__.py
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_scaffolding.py -v`
Expected: PASS

- [ ] **Step 5: コミット**

```bash
git add requirements.txt requirements-dev.txt .gitignore conftest.py src/workpulse/__init__.py tests/test_scaffolding.py
git commit -m "chore: プロジェクト雛形とworkpulseパッケージ骨格を追加"
```

---

### Task 2: `paths.py` - 日次データパスのヘルパー

**Files:**
- Create: `src/workpulse/paths.py`
- Test: `tests/test_paths.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `DATA_ROOT: Path`（モジュールグローバル、既定 `Path("data")`。テストで `monkeypatch.setattr` して差し替える前提）
  - `data_dir_for_date(d: date) -> Path`
  - `audit_path(d: date) -> Path`
  - `work_content_path(d: date) -> Path`
  - `screenshot_dir(d: date) -> Path`
  - `screenshot_path(dt: datetime) -> Path`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_paths.py
from datetime import date, datetime
from pathlib import Path

from workpulse.paths import (
    data_dir_for_date,
    audit_path,
    work_content_path,
    screenshot_dir,
    screenshot_path,
)


def test_data_dir_for_date_builds_year_month_day_path():
    assert data_dir_for_date(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26"


def test_audit_path():
    assert audit_path(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26" / "audit.parquet"


def test_work_content_path():
    assert work_content_path(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26" / "work-content.parquet"


def test_screenshot_dir():
    assert screenshot_dir(date(2026, 8, 26)) == Path("data") / "2026" / "08" / "26" / "screenshots"


def test_screenshot_path_formats_hhmm():
    dt = datetime(2026, 8, 26, 9, 30, 0)
    assert screenshot_path(dt) == Path("data") / "2026" / "08" / "26" / "screenshots" / "0930.png"
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_paths.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.paths'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/paths.py
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

DATA_ROOT = Path("data")


def data_dir_for_date(d: date) -> Path:
    return DATA_ROOT / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"


def audit_path(d: date) -> Path:
    return data_dir_for_date(d) / "audit.parquet"


def work_content_path(d: date) -> Path:
    return data_dir_for_date(d) / "work-content.parquet"


def screenshot_dir(d: date) -> Path:
    return data_dir_for_date(d) / "screenshots"


def screenshot_path(dt: datetime) -> Path:
    return screenshot_dir(dt.date()) / f"{dt.strftime('%H%M')}.png"
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_paths.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/paths.py tests/test_paths.py
git commit -m "feat: 日次データパスのヘルパーを追加"
```

---

### Task 3: `parquet_io.py` - Parquetの読み込み・1行追記

**Files:**
- Create: `src/workpulse/parquet_io.py`
- Test: `tests/test_parquet_io.py`

**Interfaces:**
- Consumes: なし（`pathlib.Path` を直接受け取る）
- Produces:
  - `read_or_empty(path: Path, columns: list[str]) -> pd.DataFrame`
  - `append_row(path: Path, row: dict, columns: list[str]) -> None`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_parquet_io.py
from datetime import datetime

import pandas as pd

from workpulse.parquet_io import read_or_empty, append_row


def test_read_or_empty_returns_empty_frame_when_file_missing(tmp_path):
    columns = ["a", "b"]
    df = read_or_empty(tmp_path / "missing.parquet", columns)
    assert list(df.columns) == columns
    assert len(df) == 0


def test_append_row_creates_file_and_appends_rows(tmp_path):
    path = tmp_path / "audit.parquet"
    columns = ["timestamp", "foreground_window_title", "foreground_process_name", "idle_seconds"]

    append_row(
        path,
        {
            "timestamp": datetime(2026, 8, 26, 9, 0, 0),
            "foreground_window_title": "A",
            "foreground_process_name": "a.exe",
            "idle_seconds": 0,
        },
        columns,
    )
    append_row(
        path,
        {
            "timestamp": datetime(2026, 8, 26, 9, 1, 0),
            "foreground_window_title": "B",
            "foreground_process_name": "b.exe",
            "idle_seconds": 5,
        },
        columns,
    )

    df = pd.read_parquet(path)
    assert len(df) == 2
    assert list(df["foreground_window_title"]) == ["A", "B"]
    assert list(df["idle_seconds"]) == [0, 5]


def test_append_row_creates_parent_directory(tmp_path):
    path = tmp_path / "2026" / "08" / "26" / "audit.parquet"
    append_row(path, {"a": 1}, ["a"])
    assert path.exists()
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_parquet_io.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.parquet_io'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/parquet_io.py
from __future__ import annotations

from pathlib import Path

import pandas as pd


def read_or_empty(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})


def append_row(path: Path, row: dict, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = read_or_empty(path, columns)
    new_row = pd.DataFrame([row], columns=columns)
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_parquet(path, index=False)
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_parquet_io.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/parquet_io.py tests/test_parquet_io.py
git commit -m "feat: Parquetの読み込み・1行追記ヘルパーを追加"
```

---

### Task 4: `activity.py` - フォアグラウンドウィンドウ情報とアイドル秒数

**Files:**
- Create: `src/workpulse/activity.py`
- Test: `tests/test_activity.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `idle_seconds_from_ticks(current_tick_ms: int, last_input_tick_ms: int) -> int`（純粋関数、Win32のtick countラップアラウンドを考慮）
  - `@dataclass ActiveWindowInfo(window_title: str, process_name: str)`
  - `read_active_window(get_foreground_hwnd, get_window_text, get_process_name_for_hwnd) -> ActiveWindowInfo`（純粋関数、Win32呼び出しは引数として注入）
  - `win32_get_foreground_hwnd() -> int | None`
  - `win32_get_window_text(hwnd) -> str`
  - `win32_get_process_name_for_hwnd(hwnd) -> str`
  - `get_idle_seconds() -> int`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_activity.py
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
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_activity.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.activity'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/activity.py
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
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_activity.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/activity.py tests/test_activity.py
git commit -m "feat: フォアグラウンドウィンドウ・アイドル秒数の取得ロジックを追加"
```

---

### Task 5: `monitor_main.py` と `monitor.py` - 1分間隔監視の本体

**Files:**
- Create: `src/workpulse/monitor_main.py`
- Create: `monitor.py`
- Test: `tests/test_monitor_main.py`

**Interfaces:**
- Consumes:
  - `workpulse.paths.audit_path(d: date) -> Path`
  - `workpulse.paths.DATA_ROOT`（テストでmonkeypatchする）
  - `workpulse.parquet_io.append_row(path, row, columns) -> None`
  - `workpulse.activity.ActiveWindowInfo`, `read_active_window`, `get_idle_seconds`, `win32_get_foreground_hwnd`, `win32_get_window_text`, `win32_get_process_name_for_hwnd`
- Produces:
  - `AUDIT_COLUMNS: list[str]`
  - `collect_and_append(now: datetime, active: ActiveWindowInfo, idle_seconds: int) -> None`
  - `run() -> None`
  - `main() -> None`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_monitor_main.py
from datetime import datetime

import pandas as pd

from workpulse.activity import ActiveWindowInfo


def test_collect_and_append_writes_expected_row(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.monitor_main import collect_and_append

    now = datetime(2026, 8, 26, 9, 31, 0)
    collect_and_append(now, ActiveWindowInfo(window_title="Notepad", process_name="notepad.exe"), 12)

    df = pd.read_parquet(paths_module.audit_path(now.date()))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["foreground_window_title"] == "Notepad"
    assert row["foreground_process_name"] == "notepad.exe"
    assert row["idle_seconds"] == 12


def test_collect_and_append_appends_second_row(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.monitor_main import collect_and_append

    now1 = datetime(2026, 8, 26, 9, 31, 0)
    now2 = datetime(2026, 8, 26, 9, 32, 0)
    collect_and_append(now1, ActiveWindowInfo(window_title="A", process_name="a.exe"), 0)
    collect_and_append(now2, ActiveWindowInfo(window_title="B", process_name="b.exe"), 3)

    df = pd.read_parquet(paths_module.audit_path(now1.date()))
    assert len(df) == 2
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_monitor_main.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.monitor_main'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/monitor_main.py
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

from workpulse.activity import (
    ActiveWindowInfo,
    get_idle_seconds,
    read_active_window,
    win32_get_foreground_hwnd,
    win32_get_process_name_for_hwnd,
    win32_get_window_text,
)
from workpulse.parquet_io import append_row
from workpulse.paths import audit_path

AUDIT_COLUMNS = ["timestamp", "foreground_window_title", "foreground_process_name", "idle_seconds"]


def collect_and_append(now: datetime, active: ActiveWindowInfo, idle_seconds: int) -> None:
    row = {
        "timestamp": now,
        "foreground_window_title": active.window_title,
        "foreground_process_name": active.process_name,
        "idle_seconds": idle_seconds,
    }
    append_row(audit_path(now.date()), row, AUDIT_COLUMNS)


def run() -> None:
    now = datetime.now()
    active = read_active_window(
        win32_get_foreground_hwnd, win32_get_window_text, win32_get_process_name_for_hwnd
    )
    idle_seconds = get_idle_seconds()
    collect_and_append(now, active, idle_seconds)


def main() -> None:
    try:
        run()
    except Exception:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "monitor_error.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        sys.exit(1)
```

```python
# monitor.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from workpulse.monitor_main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_monitor_main.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/monitor_main.py monitor.py tests/test_monitor_main.py
git commit -m "feat: 1分間隔監視プロセス(monitor.py)を追加"
```

---

### Task 6: `audit_summary.py` - 直近ログの要約

**Files:**
- Create: `src/workpulse/audit_summary.py`
- Test: `tests/test_audit_summary.py`

**Interfaces:**
- Consumes: `pandas.DataFrame`（`audit.parquet` と同じ列を持つ）
- Produces:
  - `recent_rows(df: pd.DataFrame, now: datetime, window_minutes: int = 30) -> pd.DataFrame`
  - `summarize(df: pd.DataFrame, now: datetime, window_minutes: int = 30, top_n: int = 3) -> str`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_audit_summary.py
from datetime import datetime

import pandas as pd

from workpulse.audit_summary import recent_rows, summarize


def test_recent_rows_filters_by_window():
    df = pd.DataFrame({"timestamp": [datetime(2026, 8, 26, 9, 0, 0), datetime(2026, 8, 26, 8, 0, 0)]})
    result = recent_rows(df, datetime(2026, 8, 26, 9, 30, 0), window_minutes=30)
    assert len(result) == 1


def test_summarize_with_no_rows_reports_no_records():
    df = pd.DataFrame(
        {
            "timestamp": pd.Series(dtype="datetime64[ns]"),
            "foreground_window_title": pd.Series(dtype="object"),
            "foreground_process_name": pd.Series(dtype="object"),
            "idle_seconds": pd.Series(dtype="int64"),
        }
    )
    text = summarize(df, datetime(2026, 8, 26, 9, 30, 0))
    assert "操作記録なし" in text


def test_summarize_counts_top_titles_and_processes_within_window():
    df = pd.DataFrame(
        {
            "timestamp": [
                datetime(2026, 8, 26, 9, 10, 0),
                datetime(2026, 8, 26, 9, 20, 0),
                datetime(2026, 8, 26, 8, 0, 0),
            ],
            "foreground_window_title": ["Excel - 資料", "Excel - 資料", "Old App"],
            "foreground_process_name": ["excel.exe", "excel.exe", "old.exe"],
            "idle_seconds": [0, 0, 0],
        }
    )
    text = summarize(df, datetime(2026, 8, 26, 9, 30, 0), window_minutes=30)
    assert "Excel - 資料(2)" in text
    assert "excel.exe(2)" in text
    assert "Old App" not in text
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_audit_summary.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.audit_summary'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/audit_summary.py
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def recent_rows(df: pd.DataFrame, now: datetime, window_minutes: int = 30) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = now - timedelta(minutes=window_minutes)
    return df[df["timestamp"] >= cutoff]


def summarize(df: pd.DataFrame, now: datetime, window_minutes: int = 30, top_n: int = 3) -> str:
    recent = recent_rows(df, now, window_minutes)
    if recent.empty:
        return f"直近{window_minutes}分間の操作記録なし"

    top_titles = recent["foreground_window_title"].value_counts().head(top_n)
    top_processes = recent["foreground_process_name"].value_counts().head(top_n)

    titles_text = ", ".join(f"{name}({count})" for name, count in top_titles.items() if name)
    processes_text = ", ".join(f"{name}({count})" for name, count in top_processes.items() if name)

    return (
        f"直近{window_minutes}分間のよく使われたウィンドウ: {titles_text or 'なし'}\n"
        f"直近{window_minutes}分間のよく使われたプロセス: {processes_text or 'なし'}"
    )
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_audit_summary.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/audit_summary.py tests/test_audit_summary.py
git commit -m "feat: 直近30分の監視ログ要約ロジックを追加"
```

---

### Task 7: `screenshot.py` - スクリーンショット撮影と保存

**Files:**
- Create: `src/workpulse/screenshot.py`
- Test: `tests/test_screenshot.py`

**Interfaces:**
- Consumes: `workpulse.paths.screenshot_path(dt: datetime) -> Path`
- Produces:
  - `save_screenshot(dt: datetime, capture_png_bytes: Callable[[], bytes]) -> Path`
  - `capture_png_bytes_mss() -> bytes`（実際の画面キャプチャ。テスト対象外）

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_screenshot.py
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
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_screenshot.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.screenshot'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/screenshot.py
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
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_screenshot.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/screenshot.py tests/test_screenshot.py
git commit -m "feat: スクリーンショット撮影・保存ロジックを追加"
```

---

### Task 8: `haiku.py` - Claude Haikuによる作業内容推定

**Files:**
- Create: `src/workpulse/haiku.py`
- Test: `tests/test_haiku.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `build_prompt_text(summary_text: str, screenshot_path: Path) -> str`
  - `predict_work_content(summary_text: str, screenshot_path: Path, run_command: Callable[[list[str]], subprocess.CompletedProcess] | None = None) -> str`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_haiku.py
import subprocess
from pathlib import Path

from workpulse.haiku import build_prompt_text, predict_work_content


def test_build_prompt_text_includes_summary_and_screenshot_path():
    text = build_prompt_text("要約テキスト", Path("data/2026/08/26/screenshots/0930.png"))
    assert "要約テキスト" in text
    assert "0930.png" in text


def test_predict_work_content_returns_trimmed_stdout_on_success():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="資料作成\n", stderr="")

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == "資料作成"


def test_predict_work_content_returns_empty_on_nonzero_exit():
    def fake_run(cmd):
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="error")

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == ""


def test_predict_work_content_returns_empty_on_exception():
    def fake_run(cmd):
        raise FileNotFoundError("claude command not found")

    result = predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert result == ""


def test_predict_work_content_invokes_claude_with_haiku_model():
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    predict_work_content("要約", Path("shot.png"), run_command=fake_run)
    assert captured["cmd"][0] == "claude"
    assert captured["cmd"][1] == "-p"
    assert "--model" in captured["cmd"]
    assert "haiku" in captured["cmd"]
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_haiku.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.haiku'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/haiku.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional


def build_prompt_text(summary_text: str, screenshot_path: Path) -> str:
    return (
        "あなたはユーザーの直近30分間のPC作業内容を1行で推定するアシスタントです。\n"
        f"画面スクリーンショット: {screenshot_path}\n"
        f"{summary_text}\n"
        "上記のスクリーンショットと操作ログから、ユーザーが直近30分間に行っていた作業内容を"
        "日本語で1行、簡潔に推定してください。推定した作業内容の文だけを出力してください。"
    )


def predict_work_content(
    summary_text: str,
    screenshot_path: Path,
    run_command: Optional[Callable[[list[str]], subprocess.CompletedProcess]] = None,
) -> str:
    if run_command is None:
        def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    prompt_text = build_prompt_text(summary_text, screenshot_path)
    try:
        result = run_command(["claude", "-p", prompt_text, "--model", "haiku"])
    except Exception:
        return ""

    if result.returncode != 0:
        return ""
    return result.stdout.strip()
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_haiku.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/haiku.py tests/test_haiku.py
git commit -m "feat: claude -p によるHaiku作業内容推定を追加"
```

---

### Task 9: `countdown_ui.py` - 予告カウントダウン

**Files:**
- Create: `src/workpulse/countdown_ui.py`
- Test: `tests/test_countdown_ui.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `class CountdownController(total_seconds: int, on_tick: Callable[[int], None], on_finish: Callable[[], None])`
    - `.tick() -> None`
    - `.skip() -> None`
    - `.finished -> bool`（プロパティ）
  - `run_countdown_window(total_seconds: int = 30) -> None`（tkinter実装。GUI依存のため自動テスト対象外、手動検証のみ）

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_countdown_ui.py
from workpulse.countdown_ui import CountdownController


def test_countdown_ticks_down_and_calls_on_finish_at_zero():
    ticks = []
    finished_calls = []

    controller = CountdownController(3, on_tick=ticks.append, on_finish=lambda: finished_calls.append(True))

    controller.tick()
    controller.tick()
    controller.tick()

    assert ticks == [2, 1, 0]
    assert finished_calls == [True]
    assert controller.finished is True


def test_countdown_tick_after_finished_is_noop():
    ticks = []
    finished_calls = []

    controller = CountdownController(1, on_tick=ticks.append, on_finish=lambda: finished_calls.append(True))
    controller.tick()
    controller.tick()

    assert ticks == [0]
    assert finished_calls == [True]


def test_countdown_skip_finishes_immediately():
    ticks = []
    finished_calls = []

    controller = CountdownController(30, on_tick=ticks.append, on_finish=lambda: finished_calls.append(True))
    controller.skip()

    assert controller.finished is True
    assert finished_calls == [True]
    assert ticks == []
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_countdown_ui.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.countdown_ui'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/countdown_ui.py
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
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_countdown_ui.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/countdown_ui.py tests/test_countdown_ui.py
git commit -m "feat: 予告カウントダウンのコントローラーとUIを追加"
```

---

### Task 10: `confirm_ui.py` - 作業内容確認ダイアログ

**Files:**
- Create: `src/workpulse/confirm_ui.py`
- Test: `tests/test_confirm_ui.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `determine_result(user_submitted: bool, user_text: str, predicted_text: str) -> tuple[str, str]`（純粋関数。戻り値は `(confirmed_text, status)`）
  - `run_confirm_dialog(predicted_text: str, timeout_seconds: int = 300) -> tuple[str, str]`（tkinter実装。GUI依存のため自動テスト対象外、手動検証のみ）

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_confirm_ui.py
from workpulse.confirm_ui import determine_result


def test_determine_result_when_user_submits():
    text, status = determine_result(True, "会議対応", "資料作成")
    assert text == "会議対応"
    assert status == "confirmed"


def test_determine_result_when_timeout_reached():
    text, status = determine_result(False, "", "資料作成")
    assert text == "資料作成"
    assert status == "auto_confirmed"
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_confirm_ui.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.confirm_ui'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/confirm_ui.py
from __future__ import annotations


def determine_result(user_submitted: bool, user_text: str, predicted_text: str) -> tuple[str, str]:
    if user_submitted:
        return user_text, "confirmed"
    return predicted_text, "auto_confirmed"


def run_confirm_dialog(predicted_text: str, timeout_seconds: int = 300) -> tuple[str, str]:
    """作業内容確認ダイアログを表示する。GUI依存のため自動テスト対象外(手動検証のみ)。"""
    import tkinter as tk

    result: dict = {"text": predicted_text, "status": "auto_confirmed"}

    root = tk.Tk()
    root.title("作業内容の確認")
    root.attributes("-topmost", True)

    tk.Label(root, text="直近30分の作業内容を確認・編集してください").pack(padx=12, pady=(12, 4))
    entry = tk.Text(root, width=50, height=3)
    entry.insert("1.0", predicted_text)
    entry.pack(padx=12, pady=4)

    def on_confirm() -> None:
        text, status = determine_result(True, entry.get("1.0", "end").strip(), predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    tk.Button(root, text="確定", command=on_confirm).pack(pady=(4, 12))

    def on_timeout() -> None:
        text, status = determine_result(False, "", predicted_text)
        result["text"], result["status"] = text, status
        root.destroy()

    root.after(timeout_seconds * 1000, on_timeout)
    root.bind("<Return>", lambda event: on_confirm())
    root.protocol("WM_DELETE_WINDOW", on_confirm)
    root.mainloop()

    return result["text"], result["status"]
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_confirm_ui.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/confirm_ui.py tests/test_confirm_ui.py
git commit -m "feat: 作業内容確認ダイアログのロジックとUIを追加"
```

---

### Task 11: `prompt_main.py` と `prompt.py` - 30分間隔プロンプトの本体

**Files:**
- Create: `src/workpulse/prompt_main.py`
- Create: `prompt.py`
- Test: `tests/test_prompt_main.py`

**Interfaces:**
- Consumes:
  - `workpulse.paths.audit_path`, `work_content_path`
  - `workpulse.parquet_io.append_row`, `read_or_empty`
  - `workpulse.audit_summary.summarize`
  - `workpulse.screenshot.save_screenshot`, `capture_png_bytes_mss`
  - `workpulse.haiku.predict_work_content`
  - `workpulse.countdown_ui.run_countdown_window`
  - `workpulse.confirm_ui.run_confirm_dialog`
- Produces:
  - `WORK_CONTENT_COLUMNS: list[str]`
  - `slot_bounds(now: datetime) -> tuple[datetime, datetime]`
  - `build_work_content_row(slot_start, slot_end, predicted_text, confirmed_text, status, screenshot_path) -> dict`
  - `run() -> None`
  - `main() -> None`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_prompt_main.py
from datetime import datetime
from pathlib import Path

from workpulse.prompt_main import build_work_content_row, slot_bounds


def test_slot_bounds_for_first_half_of_hour():
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 5, 0))
    assert start == datetime(2026, 8, 26, 9, 0, 0)
    assert end == datetime(2026, 8, 26, 9, 30, 0)


def test_slot_bounds_for_second_half_of_hour():
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 47, 0))
    assert start == datetime(2026, 8, 26, 9, 30, 0)
    assert end == datetime(2026, 8, 26, 10, 0, 0)


def test_slot_bounds_crosses_hour_boundary():
    start, end = slot_bounds(datetime(2026, 8, 26, 9, 58, 0))
    assert start == datetime(2026, 8, 26, 9, 30, 0)
    assert end == datetime(2026, 8, 26, 10, 0, 0)


def test_build_work_content_row_returns_expected_fields():
    row = build_work_content_row(
        datetime(2026, 8, 26, 9, 0, 0),
        datetime(2026, 8, 26, 9, 30, 0),
        "predicted",
        "confirmed",
        "confirmed",
        Path("shot.png"),
    )
    assert row == {
        "slot_start": datetime(2026, 8, 26, 9, 0, 0),
        "slot_end": datetime(2026, 8, 26, 9, 30, 0),
        "predicted_text": "predicted",
        "confirmed_text": "confirmed",
        "status": "confirmed",
        "screenshot_path": "shot.png",
    }
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_prompt_main.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.prompt_main'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/prompt_main.py
from __future__ import annotations

import sys
import traceback
from datetime import datetime, timedelta
from pathlib import Path

from workpulse.audit_summary import summarize
from workpulse.confirm_ui import run_confirm_dialog
from workpulse.countdown_ui import run_countdown_window
from workpulse.haiku import predict_work_content
from workpulse.parquet_io import append_row, read_or_empty
from workpulse.paths import audit_path, work_content_path
from workpulse.screenshot import capture_png_bytes_mss, save_screenshot

WORK_CONTENT_COLUMNS = [
    "slot_start",
    "slot_end",
    "predicted_text",
    "confirmed_text",
    "status",
    "screenshot_path",
]
AUDIT_COLUMNS = ["timestamp", "foreground_window_title", "foreground_process_name", "idle_seconds"]


def slot_bounds(now: datetime) -> tuple[datetime, datetime]:
    minute = 0 if now.minute < 30 else 30
    slot_start = now.replace(minute=minute, second=0, microsecond=0)
    slot_end = slot_start + timedelta(minutes=30)
    return slot_start, slot_end


def build_work_content_row(
    slot_start: datetime,
    slot_end: datetime,
    predicted_text: str,
    confirmed_text: str,
    status: str,
    screenshot_path: Path,
) -> dict:
    return {
        "slot_start": slot_start,
        "slot_end": slot_end,
        "predicted_text": predicted_text,
        "confirmed_text": confirmed_text,
        "status": status,
        "screenshot_path": str(screenshot_path),
    }


def run() -> None:
    now = datetime.now()
    slot_start, slot_end = slot_bounds(now)

    run_countdown_window(30)

    shot_path = save_screenshot(now, capture_png_bytes_mss)

    audit_df = read_or_empty(audit_path(now.date()), AUDIT_COLUMNS)
    summary_text = summarize(audit_df, now)

    predicted_text = predict_work_content(summary_text, shot_path)

    confirmed_text, status = run_confirm_dialog(predicted_text, timeout_seconds=300)

    row = build_work_content_row(slot_start, slot_end, predicted_text, confirmed_text, status, shot_path)
    append_row(work_content_path(now.date()), row, WORK_CONTENT_COLUMNS)


def main() -> None:
    try:
        run()
    except Exception:
        log_dir = Path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        with open(log_dir / "prompt_error.log", "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        sys.exit(1)
```

```python
# prompt.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from workpulse.prompt_main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_prompt_main.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/prompt_main.py prompt.py tests/test_prompt_main.py
git commit -m "feat: 30分間隔プロンプトプロセス(prompt.py)を追加"
```

---

### Task 12: `view_cli.py` と `view.py` - 閲覧・編集CLI

**Files:**
- Create: `src/workpulse/view_cli.py`
- Create: `view.py`
- Test: `tests/test_view_cli.py`

**Interfaces:**
- Consumes:
  - `workpulse.paths.work_content_path`, `DATA_ROOT`
  - `workpulse.parquet_io.read_or_empty`
- Produces:
  - `WORK_CONTENT_COLUMNS: list[str]`
  - `load_slots(target_date: date) -> pd.DataFrame`
  - `format_slot_line(index: int, row: pd.Series) -> str`
  - `update_confirmed_text(target_date: date, index: int, new_text: str) -> None`
  - `run_interactive(target_date: date, input_func=input, print_func=print) -> None`
  - `parse_target_date(argv: list[str]) -> date`
  - `main(argv: list[str] | None = None) -> None`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_view_cli.py
from datetime import date, datetime

import pandas as pd
import pytest

from workpulse.view_cli import (
    WORK_CONTENT_COLUMNS,
    format_slot_line,
    load_slots,
    parse_target_date,
    run_interactive,
    update_confirmed_text,
)


def _seed(tmp_path, monkeypatch, target_date):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)

    from workpulse.parquet_io import append_row

    append_row(
        paths_module.work_content_path(target_date),
        {
            "slot_start": datetime(2026, 8, 26, 9, 0, 0),
            "slot_end": datetime(2026, 8, 26, 9, 30, 0),
            "predicted_text": "資料作成",
            "confirmed_text": "資料作成",
            "status": "auto_confirmed",
            "screenshot_path": "shot1.png",
        },
        WORK_CONTENT_COLUMNS,
    )
    return paths_module


def test_load_slots_returns_empty_when_no_file(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    df = load_slots(date(2026, 8, 26))
    assert len(df) == 0
    assert list(df.columns) == WORK_CONTENT_COLUMNS


def test_load_slots_returns_seeded_rows(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    df = load_slots(date(2026, 8, 26))
    assert len(df) == 1
    assert df.iloc[0]["confirmed_text"] == "資料作成"


def test_format_slot_line_includes_time_range_status_and_text():
    row = pd.Series(
        {
            "slot_start": datetime(2026, 8, 26, 9, 0, 0),
            "slot_end": datetime(2026, 8, 26, 9, 30, 0),
            "confirmed_text": "資料作成",
            "status": "auto_confirmed",
        }
    )
    line = format_slot_line(0, row)
    assert "09:00-09:30" in line
    assert "auto_confirmed" in line
    assert "資料作成" in line


def test_update_confirmed_text_updates_row_and_marks_confirmed(tmp_path, monkeypatch):
    paths_module = _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    update_confirmed_text(date(2026, 8, 26), 0, "会議対応")
    df = load_slots(date(2026, 8, 26))
    assert df.loc[0, "confirmed_text"] == "会議対応"
    assert df.loc[0, "status"] == "confirmed"


def test_update_confirmed_text_raises_for_invalid_index(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    with pytest.raises(IndexError):
        update_confirmed_text(date(2026, 8, 26), 5, "会議対応")


def test_run_interactive_reports_no_records_when_empty(tmp_path, monkeypatch):
    from workpulse import paths as paths_module

    monkeypatch.setattr(paths_module, "DATA_ROOT", tmp_path)
    outputs = []
    run_interactive(date(2026, 8, 27), input_func=lambda prompt: "", print_func=outputs.append)
    assert any("記録はありません" in line for line in outputs)


def test_run_interactive_edits_selected_slot(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, date(2026, 8, 26))
    inputs = iter(["0", "会議対応", ""])
    outputs = []

    run_interactive(date(2026, 8, 26), input_func=lambda prompt: next(inputs), print_func=outputs.append)

    df = load_slots(date(2026, 8, 26))
    assert df.loc[0, "confirmed_text"] == "会議対応"
    assert any("保存しました" in line for line in outputs)


def test_parse_target_date():
    assert parse_target_date(["--date", "2026-08-26"]) == date(2026, 8, 26)
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_view_cli.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.view_cli'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/view_cli.py
from __future__ import annotations

import argparse
import sys
from datetime import date

import pandas as pd

from workpulse.parquet_io import read_or_empty
from workpulse.paths import work_content_path

WORK_CONTENT_COLUMNS = [
    "slot_start",
    "slot_end",
    "predicted_text",
    "confirmed_text",
    "status",
    "screenshot_path",
]


def load_slots(target_date: date) -> pd.DataFrame:
    return read_or_empty(work_content_path(target_date), WORK_CONTENT_COLUMNS)


def format_slot_line(index: int, row: pd.Series) -> str:
    slot_start = pd.Timestamp(row["slot_start"]).strftime("%H:%M")
    slot_end = pd.Timestamp(row["slot_end"]).strftime("%H:%M")
    return f"[{index}] {slot_start}-{slot_end} ({row['status']}) {row['confirmed_text']}"


def update_confirmed_text(target_date: date, index: int, new_text: str) -> None:
    path = work_content_path(target_date)
    df = read_or_empty(path, WORK_CONTENT_COLUMNS)
    if index < 0 or index >= len(df):
        raise IndexError(f"invalid slot index: {index}")
    df.loc[index, "confirmed_text"] = new_text
    df.loc[index, "status"] = "confirmed"
    df.to_parquet(path, index=False)


def run_interactive(target_date: date, input_func=input, print_func=print) -> None:
    df = load_slots(target_date)
    if df.empty:
        print_func(f"{target_date.isoformat()} の記録はありません")
        return

    for i, row in df.iterrows():
        print_func(format_slot_line(i, row))

    print_func("編集する番号を入力してください（何も入力せず終了する場合はEnter）")
    while True:
        selection = input_func("> ").strip()
        if selection == "":
            break
        if not selection.isdigit() or int(selection) not in df.index:
            print_func("無効な番号です")
            continue

        index = int(selection)
        current = df.loc[index, "confirmed_text"]
        print_func(f"現在の内容: {current}")
        new_text = input_func("新しい内容（そのまま変更しない場合はEnter）: ").strip()
        if new_text != "":
            update_confirmed_text(target_date, index, new_text)
            df = load_slots(target_date)
            print_func("保存しました")
        print_func(format_slot_line(index, df.loc[index]))


def parse_target_date(argv: list[str]) -> date:
    parser = argparse.ArgumentParser(description="作業内容の閲覧・編集")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    return date.fromisoformat(args.date)


def main(argv: list[str] | None = None) -> None:
    target_date = parse_target_date(argv if argv is not None else sys.argv[1:])
    run_interactive(target_date)
```

```python
# view.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from workpulse.view_cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_view_cli.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/view_cli.py view.py tests/test_view_cli.py
git commit -m "feat: 作業内容の閲覧・編集CLI(view.py)を追加"
```

---

### Task 13: `task_xml.py` - タスクスケジューラー用XML生成

**Files:**
- Create: `src/workpulse/task_xml.py`
- Test: `tests/test_task_xml.py`

**Interfaces:**
- Consumes: なし
- Produces:
  - `build_task_xml(python_exe: str, script_path: str, working_directory: str, start_boundary: str, repetition_interval: str, repetition_duration: str = "PT15H") -> str`
  - `write_task_xml_file(xml_body: str, path: Path) -> None`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_task_xml.py
import xml.etree.ElementTree as ET

from workpulse.task_xml import build_task_xml, write_task_xml_file

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _build_sample_xml() -> str:
    return build_task_xml(
        python_exe="C:\\venv\\Scripts\\python.exe",
        script_path="C:\\work-pulse-checker\\rebuild\\monitor.py",
        working_directory="C:\\work-pulse-checker\\rebuild",
        start_boundary="2026-01-01T07:00:00",
        repetition_interval="PT1M",
    )


def test_build_task_xml_sets_start_boundary_and_repetition():
    root = ET.fromstring(_build_sample_xml())
    trigger = root.find(".//t:CalendarTrigger", NS)
    assert trigger.find("t:StartBoundary", NS).text == "2026-01-01T07:00:00"
    assert trigger.find("t:Repetition/t:Interval", NS).text == "PT1M"
    assert trigger.find("t:Repetition/t:Duration", NS).text == "PT15H"


def test_build_task_xml_restricts_to_weekdays():
    root = ET.fromstring(_build_sample_xml())
    days = root.findall(".//t:ScheduleByWeek/t:DaysOfWeek/*", NS)
    day_tags = [ET.QName(d.tag).localname for d in days]
    assert day_tags == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def test_build_task_xml_prevents_multiple_instances():
    root = ET.fromstring(_build_sample_xml())
    policy = root.find("t:Settings/t:MultipleInstancesPolicy", NS)
    assert policy.text == "IgnoreNew"


def test_build_task_xml_sets_action_command():
    root = ET.fromstring(_build_sample_xml())
    exec_node = root.find("t:Actions/t:Exec", NS)
    assert exec_node.find("t:Command", NS).text == "C:\\venv\\Scripts\\python.exe"
    assert "monitor.py" in exec_node.find("t:Arguments", NS).text
    assert exec_node.find("t:WorkingDirectory", NS).text == "C:\\work-pulse-checker\\rebuild"


def test_write_task_xml_file_writes_utf16_with_declaration(tmp_path):
    xml_body = _build_sample_xml()
    path = tmp_path / "task.xml"
    write_task_xml_file(xml_body, path)

    content = path.read_text(encoding="utf-16")
    assert content.startswith('<?xml version="1.0" encoding="UTF-16"?>')
    assert "<Task" in content
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_task_xml.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.task_xml'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/task_xml.py
from __future__ import annotations

from pathlib import Path

TASK_XML_TEMPLATE = """<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{start_boundary}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByWeek>
        <DaysOfWeek>
          <Monday />
          <Tuesday />
          <Wednesday />
          <Thursday />
          <Friday />
        </DaysOfWeek>
        <WeeksInterval>1</WeeksInterval>
      </ScheduleByWeek>
      <Repetition>
        <Interval>{repetition_interval}</Interval>
        <Duration>{repetition_duration}</Duration>
        <StopAtDurationEnd>true</StopAtDurationEnd>
      </Repetition>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <StartWhenAvailable>false</StartWhenAvailable>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{python_exe}</Command>
      <Arguments>&quot;{script_path}&quot;</Arguments>
      <WorkingDirectory>{working_directory}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>"""


def build_task_xml(
    python_exe: str,
    script_path: str,
    working_directory: str,
    start_boundary: str,
    repetition_interval: str,
    repetition_duration: str = "PT15H",
) -> str:
    return TASK_XML_TEMPLATE.format(
        python_exe=python_exe,
        script_path=script_path,
        working_directory=working_directory,
        start_boundary=start_boundary,
        repetition_interval=repetition_interval,
        repetition_duration=repetition_duration,
    )


def write_task_xml_file(xml_body: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = '<?xml version="1.0" encoding="UTF-16"?>\n' + xml_body
    path.write_text(content, encoding="utf-16")
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_task_xml.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/task_xml.py tests/test_task_xml.py
git commit -m "feat: タスクスケジューラー登録用XML生成ロジックを追加"
```

---

### Task 14: `install_tasks_main.py` と `install_tasks.py` - タスク登録スクリプト

**Files:**
- Create: `src/workpulse/install_tasks_main.py`
- Create: `install_tasks.py`
- Test: `tests/test_install_tasks_main.py`

**Interfaces:**
- Consumes: `workpulse.task_xml.build_task_xml`, `write_task_xml_file`
- Produces:
  - `MONITOR_TASK_NAME: str`, `PROMPT_TASK_NAME: str`
  - `task_definitions(project_root: Path) -> list[dict]`
  - `install_task(task_name, script_path, repetition_interval, python_exe, project_root, xml_dir, run_command) -> None`
  - `install_all(project_root: Path, python_exe: str, run_command=None) -> None`
  - `main() -> None`

- [ ] **Step 1: テストを先に書く**

```python
# tests/test_install_tasks_main.py
import subprocess

import pytest

from workpulse.install_tasks_main import (
    MONITOR_TASK_NAME,
    PROMPT_TASK_NAME,
    install_all,
    install_task,
)


def _ok(cmd):
    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")


def test_install_all_registers_monitor_and_prompt_tasks(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _ok(cmd)

    install_all(tmp_path, python_exe="C:\\venv\\Scripts\\python.exe", run_command=fake_run)

    create_calls = [c for c in calls if "/create" in c]
    assert len(create_calls) == 2
    task_names = [c[c.index("/tn") + 1] for c in create_calls]
    assert MONITOR_TASK_NAME in task_names
    assert PROMPT_TASK_NAME in task_names


def test_install_all_deletes_existing_task_before_creating(tmp_path):
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return _ok(cmd)

    install_all(tmp_path, python_exe="C:\\venv\\Scripts\\python.exe", run_command=fake_run)

    delete_calls = [c for c in calls if "/delete" in c]
    assert len(delete_calls) == 2


def test_install_all_writes_xml_files(tmp_path):
    def fake_run(cmd):
        return _ok(cmd)

    install_all(tmp_path, python_exe="C:\\venv\\Scripts\\python.exe", run_command=fake_run)

    xml_dir = tmp_path / "logs" / "task_xml"
    assert (xml_dir / f"{MONITOR_TASK_NAME}.xml").exists()
    assert (xml_dir / f"{PROMPT_TASK_NAME}.xml").exists()


def test_install_task_raises_when_create_fails(tmp_path):
    def fake_run(cmd):
        if "/create" in cmd:
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="denied")
        return _ok(cmd)

    with pytest.raises(RuntimeError):
        install_task(
            task_name="SomeTask",
            script_path=str(tmp_path / "monitor.py"),
            repetition_interval="PT1M",
            python_exe="C:\\venv\\Scripts\\python.exe",
            project_root=tmp_path,
            xml_dir=tmp_path / "logs" / "task_xml",
            run_command=fake_run,
        )
```

- [ ] **Step 2: テストを実行し、失敗することを確認する**

Run: `pytest tests/test_install_tasks_main.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'workpulse.install_tasks_main'`)

- [ ] **Step 3: 実装する**

```python
# src/workpulse/install_tasks_main.py
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from workpulse.task_xml import build_task_xml, write_task_xml_file

MONITOR_TASK_NAME = "WorkPulseChecker_Monitor"
PROMPT_TASK_NAME = "WorkPulseChecker_Prompt"
DEFAULT_START_BOUNDARY = "2026-01-01T07:00:00"


def task_definitions(project_root: Path) -> list[dict]:
    return [
        {
            "name": MONITOR_TASK_NAME,
            "script_path": str(project_root / "monitor.py"),
            "repetition_interval": "PT1M",
        },
        {
            "name": PROMPT_TASK_NAME,
            "script_path": str(project_root / "prompt.py"),
            "repetition_interval": "PT30M",
        },
    ]


def install_task(
    task_name: str,
    script_path: str,
    repetition_interval: str,
    python_exe: str,
    project_root: Path,
    xml_dir: Path,
    run_command: Callable[[list[str]], subprocess.CompletedProcess],
) -> None:
    xml_body = build_task_xml(
        python_exe=python_exe,
        script_path=script_path,
        working_directory=str(project_root),
        start_boundary=DEFAULT_START_BOUNDARY,
        repetition_interval=repetition_interval,
    )
    xml_path = xml_dir / f"{task_name}.xml"
    write_task_xml_file(xml_body, xml_path)

    run_command(["schtasks", "/delete", "/tn", task_name, "/f"])
    result = run_command(["schtasks", "/create", "/tn", task_name, "/xml", str(xml_path), "/f"])
    if result.returncode != 0:
        raise RuntimeError(f"タスク登録に失敗しました: {task_name}\n{result.stderr}")


def install_all(project_root: Path, python_exe: str, run_command: Optional[Callable] = None) -> None:
    if run_command is None:
        def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
            return subprocess.run(cmd, capture_output=True, text=True)

    xml_dir = project_root / "logs" / "task_xml"
    for task in task_definitions(project_root):
        install_task(
            task_name=task["name"],
            script_path=task["script_path"],
            repetition_interval=task["repetition_interval"],
            python_exe=python_exe,
            project_root=project_root,
            xml_dir=xml_dir,
            run_command=run_command,
        )


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent.parent
    python_exe = sys.executable
    install_all(project_root, python_exe)
    print("タスクスケジューラーへの登録が完了しました。")
```

```python
# install_tasks.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from workpulse.install_tasks_main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: テストを実行し、成功することを確認する**

Run: `pytest tests/test_install_tasks_main.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: コミット**

```bash
git add src/workpulse/install_tasks_main.py install_tasks.py tests/test_install_tasks_main.py
git commit -m "feat: タスクスケジューラー登録スクリプト(install_tasks.py)を追加"
```

---

### Task 15: README作成と全体テスト・手動検証チェックリスト

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: なし（ドキュメントタスク）
- Produces: なし

- [ ] **Step 1: `README.md` を作成する**

```markdown
# work-pulse-checker (rebuild)

Windowsタスクスケジューラーに駆動される、常駐なしの作業監視・記録ツール。

## セットアップ

1. Python 3.11以上をインストールする
2. 仮想環境を作成し、依存関係をインストールする

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

3. [Claude Code CLI](https://docs.claude.com/) をインストールし、`claude` コマンドが使える状態にする（`prompt.py` が `claude -p ... --model haiku` を呼び出す）
4. タスクスケジューラーにタスクを登録する

   ```bash
   python install_tasks.py
   ```

   これにより以下の2つのタスクが登録される。

   - `WorkPulseChecker_Monitor`: `monitor.py` を平日7:00〜22:00の間、1分間隔で実行
   - `WorkPulseChecker_Prompt`: `prompt.py` を平日7:00〜22:00の間、30分間隔で実行

   いずれも多重起動時は新規開始しない（`MultipleInstancesPolicy=IgnoreNew`）。

## データ

```
data/YYYY/MM/DD/audit.parquet          # 1分ごとの監視ログ
data/YYYY/MM/DD/work-content.parquet   # 30分ごとの作業内容
data/YYYY/MM/DD/screenshots/HHMM.png   # プロンプト時のスクリーンショット
logs/                                   # 実行時エラーログ
```

## 記録の閲覧・編集

```bash
python view.py --date 2026-08-26
```

その日の作業内容一覧が表示される。番号を入力すると `confirmed_text` を編集できる。監視ログ（`audit.parquet`）は本ツールでは扱わない。

## テスト

```bash
pytest -v
```

## 手動検証チェックリスト（自動テスト対象外の項目）

- [ ] `python monitor.py` を実行し、`data/YYYY/MM/DD/audit.parquet` に1行追記されることを確認する
- [ ] `python prompt.py` を実行し、右下に予告カウントダウンの小窓が表示され、クリックまたは30秒経過で確認ダイアログに進むことを確認する
- [ ] 確認ダイアログにHaikuの推定テキストが初期値として表示され、編集して確定すると `work-content.parquet` に `status=confirmed` で保存されることを確認する
- [ ] 確認ダイアログを放置し、5分後に `status=auto_confirmed` で自動保存されることを確認する
- [ ] `python install_tasks.py` を実行し、タスクスケジューラー（`taskschd.msc`）に2つのタスクが登録されることを確認する
- [ ] 登録されたタスクが平日7:00〜22:00の時間帯設定になっていることをタスクスケジューラーのGUIで確認する
```

- [ ] **Step 2: 全テストスイートを実行し、すべて成功することを確認する**

Run: `pytest -v`
Expected: PASS (全テストケースが成功する。Task 1〜14で作成した `tests/` 配下のすべてのテストが対象)

- [ ] **Step 3: コミット**

```bash
git add README.md
git commit -m "docs: README作成とセットアップ・手動検証手順を追加"
```
