# src/workpulse/attendance/providers/hrmos.py
"""HRMOS勤怠（https://p.ieyasu.co/<tenant>/）向けプロバイダー。

Playwright でブラウザを操作する。DOM に依存する部分はすべて
`SELECTORS` にまとめ、画面変更時はここだけ直せば済むようにしている。

Playwright は実行時にのみ import する（この実装を使わない環境では
依存を要求しないため）。
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

from workpulse.attendance.errors import (
    AuthenticationError,
    NavigationError,
    SubmitError,
)
from workpulse.attendance.models import (
    Credentials,
    DailyRecord,
    DailyReport,
    ReportRow,
    SubmitResult,
    WorkEntry,
)
from workpulse.attendance.provider import BaseProvider

DEFAULT_BASE_URL = "https://p.ieyasu.co/gcom/"

#: ログイン後の画面はテナント配下ではなくルート直下に置かれる。
#: 例: https://p.ieyasu.co/works/2026-09, https://p.ieyasu.co/daily_reports/577415
APP_ROOT = "https://p.ieyasu.co/"

#: 画面変更時はここだけ更新する。値は Playwright のセレクター。
SELECTORS: dict[str, str] = {
    "login_id": "#user_login_id",
    "password": "#user_password",
    "login_submit": "input[type=submit]",
    # ログイン後にだけ現れる要素。これが出ればログイン成功とみなす。
    "logged_in_marker": "a[href*='logout'], a[href*='sign_out']",
    # ログイン失敗時のエラー表示。
    "login_error": ".alert, .error, #flash_alert",
    # 勤怠修正画面の入力欄（テナント設定により異なる場合があるため上書き可能）。
    "day_start": "input[name*='start_at']",
    "day_end": "input[name*='end_at']",
    "day_note": "textarea[name*='note'], input[name*='note']",
    "day_submit": "input[type=submit], button[type=submit]",
    # 日報画面の日付セレクター（option の value が日報ID、text が YYYY-MM-DD）。
    "report_date_select": "select",
    # 日次勤怠一覧の「日報へ」リンク。
    "report_link": "a[href*='/daily_reports/']",
    # 日報編集画面の各列（`reports_attributes[i][...]` の部分一致で拾う）。
    "report_category": "select[name*='service_large_category_id']",
    "report_service": "input[name*='service_name']",
    "report_plan": "input[name*='plan_time_str']",
    "report_result": "input[name*='result_time_str']",
    "report_note": "textarea[name*='notes']",
    # 行の追加・削除と登録。
    "report_add_row": ".add_daily_report",
    "report_delete_row": ".des_daily_report",
    "report_submit": "input[name='commit']",
}

#: 大分類の select が値を反映するまでの待ち時間（ミリ秒）。
CATEGORY_SETTLE_MS = 1_500

#: 日次勤怠一覧のヘッダー名 → `DailyRecord.extra` のキー。
#: ヘッダー文字列は空白を除去して突き合わせる。
WORK_COLUMNS: dict[str, str] = {
    "日付": "day",
    "勤務区分所定勤務区分": "work_type",
    "出勤時刻(打刻)(差分)": "start",
    "退勤時刻(打刻)(差分)": "end",
    "総労働時間": "total_time",
    "実労働時間": "actual_time",
    "休憩時間": "break_time",
    "予定開始時刻": "plan_start",
    "予定終了時刻": "plan_end",
    "備考": "note",
    "申請承認": "application",
}


class HrmosProvider(BaseProvider):
    """HRMOS勤怠のブラウザ操作ラッパー。"""

    name = "hrmos"

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        app_root: str = APP_ROOT,
        headless: bool = True,
        timeout_ms: int = 30_000,
        selectors: dict[str, str] | None = None,
        screenshot_dir: Path | str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.app_root = app_root.rstrip("/") + "/"
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.selectors = {**SELECTORS, **(selectors or {})}
        self.screenshot_dir = Path(screenshot_dir) if screenshot_dir else None
        # 月ごとの「日付 → 日報ID」対応表のキャッシュ（キーは "YYYY-MM"）。
        self._report_ids: dict[str, dict[date, str]] = {}
        self._playwright: Any = None
        self._browser: Any = None
        self._page: Any = None

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------
    def _ensure_page(self) -> Any:
        """ブラウザを起動してページを返す（起動済みなら使い回す）。"""
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise NavigationError(
                "playwright が未インストール。`pip install playwright` と "
                "`playwright install chromium` を実行する"
            ) from exc

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self.headless)
        self._page = self._browser.new_page()
        self._page.set_default_timeout(self.timeout_ms)
        return self._page

    def close(self) -> None:
        for obj, attr in ((self._browser, "close"), (self._playwright, "stop")):
            if obj is not None:
                try:
                    getattr(obj, attr)()
                except Exception:  # pragma: no cover - 解放時の失敗は無視する
                    pass
        self._page = None
        self._browser = None
        self._playwright = None

    # ------------------------------------------------------------------
    # 日報（日付 → URL の解決）
    # ------------------------------------------------------------------
    def month_url(self, year: int, month: int) -> str:
        """日次勤怠一覧（月次）の URL。`?d=` は効かずパスで指定する。"""
        return f"{self.app_root}works/{year:04d}-{month:02d}"

    def report_url(self, work_date: date, edit: bool = False) -> str:
        """指定日の日報 URL。

        日報 URL は日付ではなく不透明な ID（`/daily_reports/577415`）なので、
        月次画面から「日付 → ID」を引いてから組み立てる。
        """
        report_id = self.report_id(work_date)
        suffix = "/edit" if edit else ""
        return f"{self.app_root}daily_reports/{report_id}{suffix}"

    def report_id(self, work_date: date) -> str:
        """指定日の日報 ID を返す。見つからなければ NavigationError。"""
        mapping = self.report_ids_for_month(work_date.year, work_date.month)
        try:
            return mapping[work_date]
        except KeyError:
            raise NavigationError(f"{work_date} の日報が見つからない") from None

    def report_ids_for_month(
        self, year: int, month: int, refresh: bool = False
    ) -> dict[date, str]:
        """その月の「日付 → 日報ID」対応表を返す（月単位でキャッシュ）。

        月次一覧の「日報へ」リンクから任意の1日を開き、日報画面の日付
        セレクターに載っている当月全日ぶんの option を読み取る。
        """
        key = f"{year:04d}-{month:02d}"
        if not refresh and key in self._report_ids:
            return self._report_ids[key]

        page = self._ensure_page()
        try:
            page.goto(self.month_url(year, month), wait_until="domcontentloaded")
            href = page.locator(self.selectors["report_link"]).first.get_attribute("href")
        except Exception as exc:
            raise NavigationError(f"{key} の日次勤怠一覧を開けない: {exc}") from exc
        if not href:
            raise NavigationError(f"{key} に日報リンクが無い")

        page.goto(_absolute(self.app_root, href), wait_until="domcontentloaded")
        options = page.eval_on_selector_all(
            self.selectors["report_date_select"] + " option",
            "els => els.map(o => [o.value, (o.textContent || '').trim()])",
        )

        mapping: dict[date, str] = {}
        for value, text in options:
            parsed = _parse_date(text)
            if parsed is not None and value:
                mapping[parsed] = str(value)
        if not mapping:
            raise NavigationError(f"{key} の日報一覧を読み取れない")

        self._report_ids[key] = mapping
        return mapping

    def open_report(self, work_date: date, edit: bool = False) -> Any:
        """指定日の日報を開いてページを返す。"""
        page = self._ensure_page()
        try:
            page.goto(self.report_url(work_date, edit=edit), wait_until="domcontentloaded")
        except NavigationError:
            raise
        except Exception as exc:
            raise NavigationError(f"{work_date} の日報を開けない: {exc}") from exc
        return page

    # ------------------------------------------------------------------
    # 日報の読み書き
    # ------------------------------------------------------------------
    def fetch_report(self, work_date: date) -> DailyReport:
        """指定日の日報を編集画面から読み取る。

        内容が空の行（大分類も業務名も備考も無い行）は除く。
        """
        page = self.open_report(work_date, edit=True)
        rows: list[ReportRow] = []
        for index in range(self._row_count(page)):
            row = ReportRow(
                category=self._row_category_text(page, index),
                service_name=self._row_value(page, "report_service", index),
                plan_minutes=_parse_minutes(self._row_value(page, "report_plan", index)),
                result_minutes=_parse_minutes(self._row_value(page, "report_result", index)),
                note=self._row_value(page, "report_note", index),
            )
            if row.category or row.service_name or row.note:
                rows.append(row)
        return DailyReport(work_date=work_date, rows=rows)

    def submit_report(self, report: DailyReport, replace: bool = True) -> SubmitResult:
        """日報を書き込んで「登録する」を押す。

        `replace=True` は既存行を上書きし、余った既存行は空にする。
        `replace=False` は既存行の後ろに追記する。
        """
        if not report.rows:
            return SubmitResult(work_date=report.work_date, changed=False, message="入力行なし")

        page = self.open_report(report.work_date, edit=True)
        offset = 0 if replace else self._filled_row_count(page)
        needed = offset + len(report.rows)

        while self._row_count(page) < needed:
            self._add_row(page)

        for i, row in enumerate(report.rows):
            self._write_row(page, offset + i, row)

        if replace:
            # 使わなくなった既存行は空にしておく（削除はサーバー側に任せる）。
            for i in range(needed, self._row_count(page)):
                self._clear_row(page, i)

        try:
            page.click(self.selectors["report_submit"])
            page.wait_for_load_state("domcontentloaded")
        except Exception as exc:
            raise SubmitError(f"{report.work_date} の日報登録に失敗した: {exc}") from exc

        self._screenshot(f"report-{report.work_date:%Y%m%d}")
        return SubmitResult(work_date=report.work_date, changed=True)

    # ------------------------------------------------------------------
    # 日報の行操作
    # ------------------------------------------------------------------
    def _row_count(self, page: Any) -> int:
        """編集画面の行数（大分類 select の個数）。"""
        return page.locator(self.selectors["report_category"]).count()

    def _filled_row_count(self, page: Any) -> int:
        """内容が入っている行数。追記時の開始位置に使う。"""
        count = 0
        for index in range(self._row_count(page)):
            if (
                self._row_category_text(page, index)
                or self._row_value(page, "report_service", index)
                or self._row_value(page, "report_note", index)
            ):
                count += 1
        return count

    def _add_row(self, page: Any) -> None:
        """「追加」ボタンで行を1つ増やす。"""
        before = self._row_count(page)
        try:
            page.click(self.selectors["report_add_row"])
        except Exception as exc:
            raise SubmitError(f"日報の行を追加できない: {exc}") from exc
        # JS で行が挿入されるまで待つ。
        for _ in range(20):
            if self._row_count(page) > before:
                return
            page.wait_for_timeout(100)
        raise SubmitError("日報の行が増えない")

    def _write_row(self, page: Any, index: int, row: ReportRow) -> None:
        """1行ぶんを入力する。"""
        if row.category:
            self._select_category(page, index, row.category)
        self._set_row(page, "report_service", index, row.service_name)
        self._set_row(page, "report_plan", index, _format_minutes(row.plan_minutes))
        self._set_row(page, "report_result", index, _format_minutes(row.result_minutes))
        self._set_row(page, "report_note", index, row.note)

    def _clear_row(self, page: Any, index: int) -> None:
        """1行ぶんを空にする。"""
        for key in ("report_service", "report_note"):
            self._set_row(page, key, index, "")
        for key in ("report_plan", "report_result"):
            self._set_row(page, key, index, "00:00")

    def _select_category(self, page: Any, index: int, category: str) -> None:
        """大分類を選ぶ。表示名でも value（ID）でも受け付ける。"""
        locator = page.locator(self.selectors["report_category"]).nth(index)
        try:
            locator.select_option(label=category)
        except Exception:
            try:
                locator.select_option(value=category)
            except Exception as exc:
                raise SubmitError(f"大分類 {category!r} を選べない: {exc}") from exc
        # 選択に応じて画面が組み替わることがあるので落ち着くまで待つ。
        page.wait_for_timeout(CATEGORY_SETTLE_MS)

    def _row_category_text(self, page: Any, index: int) -> str:
        """その行で選択中の大分類の表示名。未選択なら空。"""
        locator = page.locator(self.selectors["report_category"]).nth(index)
        if locator.count() == 0:
            return ""
        text = locator.evaluate(
            "s => s.value ? (s.options[s.selectedIndex].textContent || '').trim() : ''"
        )
        return str(text or "").strip()

    def _row_value(self, page: Any, key: str, index: int) -> str:
        """その行の入力値。要素が無ければ空。"""
        locator = page.locator(self.selectors[key]).nth(index)
        if locator.count() == 0:
            return ""
        return (locator.input_value() or "").strip()

    def _set_row(self, page: Any, key: str, index: int, value: str) -> None:
        """その行に入力する。要素が無ければ何もしない。"""
        locator = page.locator(self.selectors[key]).nth(index)
        if locator.count() == 0:
            return
        try:
            locator.fill(value)
        except Exception as exc:
            raise SubmitError(f"{key}[{index}] に入力できない: {exc}") from exc

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------
    def login(self, credentials: Credentials) -> None:
        page = self._ensure_page()
        page.goto(self.base_url + "login", wait_until="domcontentloaded")
        page.fill(self.selectors["login_id"], credentials.login_id)
        page.fill(self.selectors["password"], credentials.password)
        page.click(self.selectors["login_submit"])
        page.wait_for_load_state("domcontentloaded")

        if "login" in page.url:
            raise AuthenticationError(
                f"ログインに失敗した: {self._error_text(page) or page.url}"
            )

    def fetch_day(self, work_date: date) -> DailyRecord | None:
        """指定日の勤怠実績を日次勤怠一覧（月次）から読み取る。

        行が見つからなければ None。打刻が無い日（休日など）も
        勤務区分は取れるので、行があれば `DailyRecord` を返す。
        """
        cells = self._work_row(work_date)
        if cells is None:
            return None

        return DailyRecord(
            work_date=work_date,
            start_at=_parse_time(work_date, _first_time(cells.get("start", ""))),
            end_at=_parse_time(work_date, _first_time(cells.get("end", ""))),
            break_minutes=_parse_minutes(cells.get("break_time", "")),
            note=cells.get("note", ""),
            status=_first_token(cells.get("work_type", "")),
            extra=cells,
        )

    def _work_row(self, work_date: date) -> dict[str, str] | None:
        """日次勤怠一覧から指定日の行を「列名 → 値」で返す。"""
        page = self._ensure_page()
        try:
            page.goto(self.month_url(work_date.year, work_date.month), wait_until="domcontentloaded")
        except Exception as exc:
            raise NavigationError(f"{work_date} の日次勤怠一覧を開けない: {exc}") from exc

        table = page.evaluate(
            """() => ({
              heads: [...document.querySelectorAll('thead th')]
                .map(e => (e.innerText || '').replace(/\\s+/g, '').trim()),
              rows: [...document.querySelectorAll('tbody tr')].map(
                tr => [...tr.querySelectorAll('td,th')]
                  .map(e => (e.innerText || '').replace(/\\s+/g, ' ').trim())
              ),
            })"""
        )

        heads = table["heads"]
        for cells in table["rows"]:
            if not cells or not cells[0].startswith(f"{work_date.day:02d} "):
                continue
            named: dict[str, str] = {}
            for head, value in zip(heads, cells):
                key = WORK_COLUMNS.get(head)
                if key:
                    named[key] = value
            return named
        return None

    def submit_day(self, entry: WorkEntry) -> SubmitResult:
        page = self._goto_day(entry.work_date)
        changed = False
        if entry.start_at is not None:
            self._write(page, "day_start", entry.start_at.strftime("%H:%M"))
            changed = True
        if entry.end_at is not None:
            self._write(page, "day_end", entry.end_at.strftime("%H:%M"))
            changed = True
        if entry.note:
            self._write(page, "day_note", entry.note)
            changed = True

        if not changed:
            return SubmitResult(work_date=entry.work_date, changed=False, message="更新項目なし")

        try:
            page.click(self.selectors["day_submit"])
            page.wait_for_load_state("domcontentloaded")
        except Exception as exc:
            raise SubmitError(f"{entry.work_date} の登録に失敗した: {exc}") from exc

        self._screenshot(f"submit-{entry.work_date:%Y%m%d}")
        return SubmitResult(work_date=entry.work_date, changed=True)

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------
    def day_url(self, work_date: date) -> str:
        """指定日の勤怠修正画面 URL。URL 体系が変わったらここを直す。"""
        return f"{self.base_url}attendance/edit?date={work_date:%Y-%m-%d}"

    def _goto_day(self, work_date: date) -> Any:
        page = self._ensure_page()
        try:
            page.goto(self.day_url(work_date), wait_until="domcontentloaded")
        except Exception as exc:
            raise NavigationError(f"{work_date} の画面へ遷移できない: {exc}") from exc
        return page

    def _read(self, page: Any, key: str) -> str:
        locator = page.locator(self.selectors[key]).first
        if locator.count() == 0:
            return ""
        try:
            return (locator.input_value() or "").strip()
        except Exception:
            return (locator.inner_text() or "").strip()

    def _write(self, page: Any, key: str, value: str) -> None:
        selector = self.selectors[key]
        try:
            page.fill(selector, value)
        except Exception as exc:
            raise SubmitError(f"{key} ({selector}) に入力できない: {exc}") from exc

    def _error_text(self, page: Any) -> str:
        locator = page.locator(self.selectors["login_error"]).first
        if locator.count() == 0:
            return ""
        return (locator.inner_text() or "").strip()

    def _screenshot(self, stem: str) -> Path | None:
        """証跡スクリーンショットを保存する（設定時のみ）。"""
        if self.screenshot_dir is None or self._page is None:
            return None
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{stem}.png"
        self._page.screenshot(path=str(path), full_page=True)
        return path


def _parse_time(work_date: date, text: str) -> datetime | None:
    """"09:30" のような文字列をその日の datetime にする。"""
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return datetime.combine(work_date, parsed.time())
    return None


def _parse_date(text: str) -> date | None:
    """"2026-09-01" を date にする。解釈できなければ None。"""
    text = (text or "").strip()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _absolute(root: str, href: str) -> str:
    """`/daily_reports/123` のような相対 href を絶対 URL にする。"""
    if href.startswith("http"):
        return href
    return root.rstrip("/") + "/" + href.lstrip("/")


def _parse_minutes(text: str) -> int | None:
    """"01:30" を分（90）にする。"00:00" や空は None。"""
    text = (text or "").strip()
    if not text:
        return None
    hours, _, minutes = text.partition(":")
    try:
        total = int(hours) * 60 + int(minutes or 0)
    except ValueError:
        return None
    return total or None


def _format_minutes(minutes: int | None) -> str:
    """分を "01:30" 形式にする。None は "00:00"。"""
    if not minutes or minutes < 0:
        return "00:00"
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _first_time(text: str) -> str:
    """"08:32 08:32 0:00" のような連結セルから先頭の時刻を取り出す。

    未打刻を表す "0:00" は時刻として扱わない。
    """
    for token in (text or "").split():
        if ":" not in token:
            continue
        if token in ("0:00", "00:00"):
            return ""
        return token
    return ""


def _first_token(text: str) -> str:
    """"有休(PM) 有休(PM)" のような連結セルから先頭語を取り出す。"""
    parts = (text or "").split()
    return parts[0] if parts else ""
