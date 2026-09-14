# tests/test_attendance.py
"""勤怠ラッパー層のテスト（実サービスには接続しない）。"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from workpulse.attendance import registry
from workpulse.attendance.config import AttendanceConfig, load_config
from workpulse.attendance.errors import NotSupportedError
from workpulse.attendance.models import Credentials, SubmitResult, WorkEntry
from workpulse.attendance.provider import AttendanceProvider, BaseProvider
from workpulse.attendance.service import open_provider


class FakeProvider(BaseProvider):
    """テスト用のダミー勤怠サービス。"""

    name = "fake"

    def __init__(self, base_url: str = "", **options):
        self.base_url = base_url
        self.options = options
        self.logged_in: Credentials | None = None
        self.submitted: list[WorkEntry] = []
        self.closed = False

    def login(self, credentials: Credentials) -> None:
        self.logged_in = credentials

    def submit_day(self, entry: WorkEntry) -> SubmitResult:
        self.submitted.append(entry)
        return SubmitResult(work_date=entry.work_date, changed=True)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_registered():
    created: list[FakeProvider] = []

    def factory(**kwargs):
        provider = FakeProvider(**kwargs)
        created.append(provider)
        return provider

    registry.register("fake", factory)
    return created


def test_fake_provider_satisfies_protocol(fake_registered):
    assert isinstance(FakeProvider(), AttendanceProvider)


def test_open_provider_logs_in_and_closes(fake_registered):
    config = AttendanceConfig(
        provider="fake",
        base_url="https://example.test/",
        login_id="u",
        password="p",
        options={"headless": False},
    )
    entry = WorkEntry(
        work_date=date(2026, 9, 11),
        start_at=datetime(2026, 9, 11, 9, 0),
        end_at=datetime(2026, 9, 11, 18, 0),
    )

    with open_provider(config) as provider:
        result = provider.submit_day(entry)

    assert result.changed is True
    created = fake_registered[0]
    assert created.logged_in == Credentials(login_id="u", password="p")
    assert created.base_url == "https://example.test/"
    assert created.options == {"headless": False}
    assert created.closed is True


def test_open_provider_closes_on_error(fake_registered):
    config = AttendanceConfig(provider="fake", login_id="u", password="p")
    with pytest.raises(RuntimeError):
        with open_provider(config):
            raise RuntimeError("boom")
    assert fake_registered[0].closed is True


def test_unsupported_operation_raises(fake_registered):
    with pytest.raises(NotSupportedError):
        FakeProvider().fetch_day(date(2026, 9, 11))


def test_registry_reports_unknown_provider():
    with pytest.raises(KeyError):
        registry.create("no-such-service")


def test_registry_includes_builtin_hrmos():
    assert "hrmos" in registry.available()


def test_load_config_prefers_env(tmp_path):
    path = tmp_path / "attendance.json"
    path.write_text(
        json.dumps(
            {
                "provider": "hrmos",
                "base_url": "https://p.ieyasu.co/gcom/",
                "login_id": "file-user",
                "options": {"headless": True},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path, env={"WORKPULSE_ATTENDANCE_PASSWORD": "secret"})

    assert config.provider == "hrmos"
    assert config.login_id == "file-user"
    assert config.password == "secret"
    assert config.provider_kwargs() == {
        "headless": True,
        "base_url": "https://p.ieyasu.co/gcom/",
    }


def test_load_config_requires_provider(tmp_path):
    path = tmp_path / "attendance.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path, env={})


def test_load_dotenv_parses_pairs(tmp_path):
    from workpulse.attendance.config import load_dotenv

    path = tmp_path / ".env"
    path.write_text(
        "# コメント\n"
        "\n"
        "WORKPULSE_ATTENDANCE_LOGIN_ID=env-user\n"
        'WORKPULSE_ATTENDANCE_PASSWORD="sec ret"\n'
        "BROKEN_LINE\n",
        encoding="utf-8",
    )

    assert load_dotenv(path) == {
        "WORKPULSE_ATTENDANCE_LOGIN_ID": "env-user",
        "WORKPULSE_ATTENDANCE_PASSWORD": "sec ret",
    }


def test_load_dotenv_missing_file(tmp_path):
    from workpulse.attendance.config import load_dotenv

    assert load_dotenv(tmp_path / "nope") == {}


def test_load_config_reads_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKPULSE_ATTENDANCE_LOGIN_ID", raising=False)
    monkeypatch.delenv("WORKPULSE_ATTENDANCE_PASSWORD", raising=False)

    config_path = tmp_path / "attendance.json"
    config_path.write_text(json.dumps({"provider": "hrmos", "login_id": "file-user"}), encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text(
        "WORKPULSE_ATTENDANCE_LOGIN_ID=dotenv-user\nWORKPULSE_ATTENDANCE_PASSWORD=dotenv-pass\n",
        encoding="utf-8",
    )

    config = load_config(config_path, env_path=env_path)

    assert config.login_id == "dotenv-user"
    assert config.password == "dotenv-pass"


def test_real_env_wins_over_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKPULSE_ATTENDANCE_PASSWORD", "from-os")

    config_path = tmp_path / "attendance.json"
    config_path.write_text(json.dumps({"provider": "hrmos"}), encoding="utf-8")
    env_path = tmp_path / ".env"
    env_path.write_text("WORKPULSE_ATTENDANCE_PASSWORD=from-dotenv\n", encoding="utf-8")

    assert load_config(config_path, env_path=env_path).password == "from-os"
