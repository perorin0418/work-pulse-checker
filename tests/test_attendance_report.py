# tests/test_attendance_report.py
"""日報の読み書きのテスト。Playwright の Locator を偽物に差し替える。"""
from __future__ import annotations

from datetime import date

import pytest

from workpulse.attendance.errors import SubmitError
from workpulse.attendance.models import DailyReport, ReportRow
from workpulse.attendance.providers.hrmos import (
    HrmosProvider,
    _format_minutes,
    _parse_minutes,
)


class Cell:
    """1つの入力欄。"""

    def __init__(self, value: str = "", label: str = ""):
        self.value = value
        self.label = label  # select の選択中ラベル

    def input_value(self) -> str:
        return self.value

    def fill(self, value: str) -> None:
        self.value = value

    def count(self) -> int:
        return 1

    def select_option(self, label: str | None = None, value: str | None = None) -> None:
        if label is not None:
            if label not in ("直接原価", "【共通】会議直接ＰＪ以外"):
                raise ValueError(f"no such label: {label}")
            self.label = label
            self.value = {"直接原価": "1", "【共通】会議直接ＰＪ以外": "2"}[label]
            return
        self.value = value or ""
        self.label = f"ID:{value}"

    def evaluate(self, script: str):
        return self.label if self.value else ""


class Row:
    def __init__(self):
        self.cells = {
            "report_category": Cell(),
            "report_service": Cell(),
            "report_plan": Cell("00:00"),
            "report_result": Cell("00:00"),
            "report_note": Cell(),
        }


class Group:
    """同種セルの集合。`nth()` / `count()` を提供する。"""

    def __init__(self, page, key: str):
        self.page = page
        self.key = key

    def count(self) -> int:
        return len(self.page.rows)

    def nth(self, index: int) -> Cell:
        if index >= len(self.page.rows):
            return Cell()  # 存在しない行
        return self.page.rows[index].cells[self.key]

    @property
    def first(self):
        return self.nth(0)


class ReportPage:
    """日報編集画面の偽物。"""

    def __init__(self, rows: int = 1, selectors: dict[str, str] | None = None):
        self.rows = [Row() for _ in range(rows)]
        self.selectors = selectors or {}
        self.clicks: list[str] = []
        self.goto_urls: list[str] = []
        self.url = ""
        self.add_broken = False

    # --- Playwright 互換 API ---
    def goto(self, url: str, wait_until: str = "") -> None:
        self.goto_urls.append(url)
        self.url = url

    def wait_for_load_state(self, state: str = "") -> None:
        pass

    def wait_for_timeout(self, ms: int) -> None:
        pass

    def click(self, selector: str) -> None:
        self.clicks.append(selector)
        if selector == ".add_daily_report" and not self.add_broken:
            self.rows.append(Row())

    def locator(self, selector: str):
        for key, sel in self.selectors.items():
            if sel == selector:
                return Group(self, key)
        return Group(self, "report_category")


@pytest.fixture
def provider(monkeypatch):
    def make(rows: int = 1):
        prov = HrmosProvider()
        page = ReportPage(rows, selectors=prov.selectors)
        monkeypatch.setattr(prov, "_ensure_page", lambda: page)
        monkeypatch.setattr(prov, "report_url", lambda d, edit=False: f"/daily_reports/1{'/edit' if edit else ''}")
        prov._page = page
        prov.page = page
        return prov, page

    return make


def test_fetch_report_skips_empty_rows(provider):
    prov, page = provider(2)
    page.rows[0].cells["report_category"].select_option(label="直接原価")
    page.rows[0].cells["report_service"].fill("設計")
    page.rows[0].cells["report_result"].fill("01:30")

    report = prov.fetch_report(date(2026, 9, 11))

    assert len(report.rows) == 1
    row = report.rows[0]
    assert row.category == "直接原価"
    assert row.service_name == "設計"
    assert row.result_minutes == 90
    assert row.plan_minutes is None  # "00:00" は未入力扱い


def test_submit_report_writes_single_row(provider):
    prov, page = provider(1)

    result = prov.submit_report(
        DailyReport(
            work_date=date(2026, 9, 11),
            rows=[ReportRow(category="直接原価", service_name="実装", result_minutes=480, note="メモ")],
        )
    )

    assert result.changed is True
    cells = page.rows[0].cells
    assert cells["report_category"].value == "1"
    assert cells["report_service"].value == "実装"
    assert cells["report_result"].value == "08:00"
    assert cells["report_note"].value == "メモ"
    assert page.clicks[-1] == "input[name='commit']"


def test_submit_report_adds_rows_as_needed(provider):
    prov, page = provider(1)

    prov.submit_report(
        DailyReport(
            work_date=date(2026, 9, 11),
            rows=[
                ReportRow(service_name="A", result_minutes=60),
                ReportRow(service_name="B", result_minutes=120),
                ReportRow(service_name="C", result_minutes=30),
            ],
        )
    )

    assert len(page.rows) == 3
    assert page.clicks.count(".add_daily_report") == 2
    assert [r.cells["report_service"].value for r in page.rows] == ["A", "B", "C"]
    assert [r.cells["report_result"].value for r in page.rows] == ["01:00", "02:00", "00:30"]


def test_submit_report_replace_clears_leftover_rows(provider):
    prov, page = provider(2)
    page.rows[1].cells["report_service"].fill("古い行")
    page.rows[1].cells["report_note"].fill("古い備考")
    page.rows[1].cells["report_result"].fill("03:00")

    prov.submit_report(
        DailyReport(work_date=date(2026, 9, 11), rows=[ReportRow(service_name="新しい行")])
    )

    assert page.rows[0].cells["report_service"].value == "新しい行"
    assert page.rows[1].cells["report_service"].value == ""
    assert page.rows[1].cells["report_note"].value == ""
    assert page.rows[1].cells["report_result"].value == "00:00"


def test_submit_report_append_keeps_existing(provider):
    prov, page = provider(1)
    page.rows[0].cells["report_service"].fill("既存")

    prov.submit_report(
        DailyReport(work_date=date(2026, 9, 11), rows=[ReportRow(service_name="追記")]),
        replace=False,
    )

    assert page.rows[0].cells["report_service"].value == "既存"
    assert page.rows[1].cells["report_service"].value == "追記"


def test_submit_report_without_rows_is_noop(provider):
    prov, page = provider(1)

    result = prov.submit_report(DailyReport(work_date=date(2026, 9, 11), rows=[]))

    assert result.changed is False
    assert page.clicks == []


def test_category_falls_back_to_value(provider):
    prov, page = provider(1)

    prov.submit_report(
        DailyReport(work_date=date(2026, 9, 11), rows=[ReportRow(category="72", service_name="休暇")])
    )

    assert page.rows[0].cells["report_category"].value == "72"


def test_unknown_category_raises(provider):
    prov, page = provider(1)

    class Strict(Cell):
        def select_option(self, label=None, value=None):
            raise ValueError("no option")

    page.rows[0].cells["report_category"] = Strict()

    with pytest.raises(SubmitError):
        prov.submit_report(
            DailyReport(work_date=date(2026, 9, 11), rows=[ReportRow(category="存在しない")])
        )


def test_add_row_failure_raises(provider):
    prov, page = provider(1)
    page.add_broken = True

    with pytest.raises(SubmitError):
        prov.submit_report(
            DailyReport(
                work_date=date(2026, 9, 11),
                rows=[ReportRow(service_name="A"), ReportRow(service_name="B")],
            )
        )


@pytest.mark.parametrize(
    "text,expected",
    [("01:30", 90), ("08:00", 480), ("00:00", None), ("", None), ("あ", None)],
)
def test_parse_minutes(text, expected):
    assert _parse_minutes(text) == expected


@pytest.mark.parametrize(
    "minutes,expected",
    [(90, "01:30"), (480, "08:00"), (0, "00:00"), (None, "00:00"), (-5, "00:00")],
)
def test_format_minutes(minutes, expected):
    assert _format_minutes(minutes) == expected
