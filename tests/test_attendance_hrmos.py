# tests/test_attendance_hrmos.py
"""HRMOSプロバイダーのテスト。ブラウザは偽物に差し替えて実接続しない。"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from workpulse.attendance.errors import AuthenticationError
from workpulse.attendance.models import Credentials, WorkEntry
from workpulse.attendance.providers.hrmos import HrmosProvider, _parse_time


class StubLocator:
    def __init__(self, value: str | None):
        self._value = value

    @property
    def first(self):
        return self

    def count(self) -> int:
        return 0 if self._value is None else 1

    def input_value(self) -> str:
        return self._value or ""

    def inner_text(self) -> str:
        return self._value or ""


class StubPage:
    """Playwright の Page のうち、本実装が使う API だけを模倣する。"""

    def __init__(self, url: str = "", values: dict[str, str] | None = None):
        self.url = url
        self.values = values or {}
        self.filled: dict[str, str] = {}
        self.clicks: list[str] = []
        self.goto_urls: list[str] = []

    def set_default_timeout(self, ms: int) -> None:
        self.timeout = ms

    def goto(self, url: str, wait_until: str = "") -> None:
        self.goto_urls.append(url)
        self.url = url

    def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value

    def click(self, selector: str) -> None:
        self.clicks.append(selector)

    def wait_for_load_state(self, state: str = "") -> None:
        pass

    def locator(self, selector: str) -> StubLocator:
        return StubLocator(self.values.get(selector))


@pytest.fixture
def provider_with(monkeypatch):
    def make(page: StubPage) -> HrmosProvider:
        provider = HrmosProvider(base_url="https://p.ieyasu.co/gcom")
        monkeypatch.setattr(provider, "_ensure_page", lambda: page)
        provider._page = page
        return provider

    return make


def test_login_success(provider_with):
    page = StubPage()
    provider = provider_with(page)
    # ログイン後は /login 以外の URL に遷移する想定。
    page.click = lambda selector: setattr(page, "url", "https://p.ieyasu.co/gcom/dashboard")

    provider.login(Credentials(login_id="user", password="pass"))

    assert page.filled["#user_login_id"] == "user"
    assert page.filled["#user_password"] == "pass"


def test_login_failure_raises(provider_with):
    page = StubPage(values={".alert, .error, #flash_alert": "ログインIDまたはパスワードが違います"})
    provider = provider_with(page)
    page.click = lambda selector: setattr(page, "url", "https://p.ieyasu.co/gcom/login")

    with pytest.raises(AuthenticationError) as exc:
        provider.login(Credentials(login_id="user", password="bad"))
    assert "パスワードが違います" in str(exc.value)


def test_submit_day_fills_and_submits(provider_with):
    page = StubPage()
    provider = provider_with(page)

    result = provider.submit_day(
        WorkEntry(
            work_date=date(2026, 9, 11),
            start_at=datetime(2026, 9, 11, 9, 0),
            end_at=datetime(2026, 9, 11, 18, 0),
            note="実装作業",
        )
    )

    assert result.changed is True
    assert page.filled["input[name*='start_at']"] == "09:00"
    assert page.filled["input[name*='end_at']"] == "18:00"
    assert page.clicks == ["input[type=submit], button[type=submit]"]
    assert "date=2026-09-11" in page.goto_urls[0]


def test_submit_day_without_values_does_nothing(provider_with):
    page = StubPage()
    result = provider_with(page).submit_day(WorkEntry(work_date=date(2026, 9, 11)))

    assert result.changed is False
    assert page.clicks == []


def test_custom_selectors_override():
    provider = HrmosProvider(selectors={"login_id": "#custom"})
    assert provider.selectors["login_id"] == "#custom"
    assert provider.selectors["password"] == "#user_password"


@pytest.mark.parametrize(
    "text,expected",
    [("09:30", datetime(2026, 9, 11, 9, 30)), ("", None), ("あ", None)],
)
def test_parse_time(text, expected):
    assert _parse_time(date(2026, 9, 11), text) == expected


class ReportStubPage(StubPage):
    """日報ID解決のための月次一覧 → 日報画面の遷移を模した偽ページ。"""

    def __init__(self, link_href: str | None, options: list[list[str]]):
        super().__init__()
        self.link_href = link_href
        self.options = options

    def locator(self, selector: str):
        page = self

        class Link:
            @property
            def first(self):
                return self

            def count(self) -> int:
                return 0 if page.link_href is None else 1

            def get_attribute(self, name: str):
                return page.link_href

        return Link()

    def eval_on_selector_all(self, selector: str, script: str):
        return self.options


@pytest.fixture
def report_provider(monkeypatch):
    def make(page):
        provider = HrmosProvider()
        monkeypatch.setattr(provider, "_ensure_page", lambda: page)
        provider._page = page
        return provider

    return make


def _september_options():
    return [[str(577414 + d), f"2026-09-{d:02d}"] for d in range(1, 31)]


def test_month_url_uses_path_not_query():
    assert HrmosProvider().month_url(2026, 9) == "https://p.ieyasu.co/works/2026-09"


def test_report_ids_for_month_builds_mapping(report_provider):
    page = ReportStubPage("/daily_reports/577415", _september_options())
    provider = report_provider(page)

    mapping = provider.report_ids_for_month(2026, 9)

    assert len(mapping) == 30
    assert mapping[date(2026, 9, 1)] == "577415"
    assert mapping[date(2026, 9, 30)] == "577444"
    # 月次一覧 → 日報画面の順に辿っている。
    assert page.goto_urls[0] == "https://p.ieyasu.co/works/2026-09"
    assert page.goto_urls[1] == "https://p.ieyasu.co/daily_reports/577415"


def test_report_ids_are_cached(report_provider):
    page = ReportStubPage("/daily_reports/577415", _september_options())
    provider = report_provider(page)

    provider.report_ids_for_month(2026, 9)
    provider.report_ids_for_month(2026, 9)

    assert len(page.goto_urls) == 2  # 2回目はキャッシュから返る


def test_report_ids_refresh_bypasses_cache(report_provider):
    page = ReportStubPage("/daily_reports/577415", _september_options())
    provider = report_provider(page)

    provider.report_ids_for_month(2026, 9)
    provider.report_ids_for_month(2026, 9, refresh=True)

    assert len(page.goto_urls) == 4


def test_report_url_resolves_id(report_provider):
    provider = report_provider(ReportStubPage("/daily_reports/577415", _september_options()))

    assert provider.report_url(date(2026, 9, 11)) == "https://p.ieyasu.co/daily_reports/577425"
    assert (
        provider.report_url(date(2026, 9, 11), edit=True)
        == "https://p.ieyasu.co/daily_reports/577425/edit"
    )


def test_report_id_missing_date_raises(report_provider):
    from workpulse.attendance.errors import NavigationError

    # 8月31日ぶんの option は9月の一覧に無いので解決できない。
    provider = report_provider(ReportStubPage("/daily_reports/577415", _september_options()))
    provider._report_ids["2026-08"] = {}
    with pytest.raises(NavigationError):
        provider.report_id(date(2026, 8, 31))


def test_report_ids_without_link_raises(report_provider):
    from workpulse.attendance.errors import NavigationError

    provider = report_provider(ReportStubPage(None, []))
    with pytest.raises(NavigationError):
        provider.report_ids_for_month(2026, 9)


def test_report_ids_with_empty_options_raises(report_provider):
    from workpulse.attendance.errors import NavigationError

    provider = report_provider(ReportStubPage("/daily_reports/1", [["", "見出し"]]))
    with pytest.raises(NavigationError):
        provider.report_ids_for_month(2026, 9)


def test_open_report_navigates(report_provider):
    page = ReportStubPage("/daily_reports/577415", _september_options())
    provider = report_provider(page)

    provider.open_report(date(2026, 9, 2))

    assert page.goto_urls[-1] == "https://p.ieyasu.co/daily_reports/577416"


def test_absolute_url_helper():
    from workpulse.attendance.providers.hrmos import _absolute

    assert _absolute("https://p.ieyasu.co/", "/daily_reports/1") == "https://p.ieyasu.co/daily_reports/1"
    assert _absolute("https://p.ieyasu.co/", "https://other/x") == "https://other/x"


def test_parse_date_helper():
    from workpulse.attendance.providers.hrmos import _parse_date

    assert _parse_date("2026-09-01") == date(2026, 9, 1)
    assert _parse_date("ヘッダ") is None


class WorkTablePage(StubPage):
    """日次勤怠一覧の偽ページ。"""

    HEADS = [
        "日付",
        "勤務区分所定勤務区分",
        "出勤時刻(打刻)(差分)",
        "退勤時刻(打刻)(差分)",
        "総労働時間",
        "実労働時間",
        "休憩時間",
        "予定開始時刻",
        "予定終了時刻",
        "備考",
        "申請承認",
    ]

    def __init__(self, rows):
        super().__init__()
        self.rows = rows

    def evaluate(self, script: str):
        return {"heads": self.HEADS, "rows": self.rows}


@pytest.fixture
def work_provider(monkeypatch):
    def make(rows):
        provider = HrmosProvider()
        page = WorkTablePage(rows)
        monkeypatch.setattr(provider, "_ensure_page", lambda: page)
        provider._page = page
        return provider, page

    return make


def _row_11():
    return [
        "11 金",
        "有休(PM) 有休(PM)",
        "08:32 08:32 0:00",
        "12:08 12:08 0:00",
        "7:36",
        "3:36",
        "0:00",
        "08:00",
        "13:00 翌日",
        "通院してきます",
        "申請",
    ]


def test_fetch_day_reads_work_table(work_provider):
    provider, page = work_provider([["10 木", *[""] * 10], _row_11()])

    rec = provider.fetch_day(date(2026, 9, 11))

    assert rec is not None
    assert rec.status == "有休(PM)"
    assert rec.start_at == datetime(2026, 9, 11, 8, 32)
    assert rec.end_at == datetime(2026, 9, 11, 12, 8)
    assert rec.note == "通院してきます"
    assert rec.extra["actual_time"] == "3:36"
    assert rec.extra["total_time"] == "7:36"
    assert page.goto_urls[-1] == "https://p.ieyasu.co/works/2026-09"


def test_fetch_day_returns_none_when_row_absent(work_provider):
    provider, _ = work_provider([["10 木", *[""] * 10]])
    assert provider.fetch_day(date(2026, 9, 11)) is None


def test_fetch_day_handles_holiday_row(work_provider):
    row = ["06 日", "日曜(法定休日) 休日", "0:00", "0:00", "0:00", "0:00", "0:00", "", "", "", ""]
    provider, _ = work_provider([row])

    rec = provider.fetch_day(date(2026, 9, 6))

    assert rec is not None
    assert rec.status == "日曜(法定休日)"
    assert rec.start_at is None  # "0:00" は時刻として扱わない


def test_first_time_and_token_helpers():
    from workpulse.attendance.providers.hrmos import _first_time, _first_token

    assert _first_time("08:32 08:32 0:00") == "08:32"
    assert _first_time("0:00") == ""  # 未打刻
    assert _first_time("") == ""
    assert _first_token("有休(PM) 有休(PM)") == "有休(PM)"
    assert _first_token("") == ""
