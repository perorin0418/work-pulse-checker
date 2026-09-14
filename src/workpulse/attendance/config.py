# src/workpulse/attendance/config.py
"""勤怠プロバイダーの設定読み込み。

設定ファイル（既定 `config/attendance.json`）の例:

    {
      "provider": "hrmos",
      "base_url": "https://p.ieyasu.co/gcom/",
      "login_id": "user@example.com",
      "options": {"headless": true}
    }

パスワードはファイルに書かず環境変数 `WORKPULSE_ATTENDANCE_PASSWORD`
（`login_id` も `WORKPULSE_ATTENDANCE_LOGIN_ID` で上書き可）から読む。
環境変数はリポジトリ直下の `.env` からも読み込む（外部ライブラリ不要の簡易実装）。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workpulse.attendance.models import Credentials

DEFAULT_CONFIG_PATH = Path("config") / "attendance.json"
DEFAULT_ENV_PATH = Path(".env")

ENV_LOGIN_ID = "WORKPULSE_ATTENDANCE_LOGIN_ID"
ENV_PASSWORD = "WORKPULSE_ATTENDANCE_PASSWORD"


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    """`.env` を読んで辞書で返す（ファイルが無ければ空）。

    対応するのは `KEY=VALUE` 形式のみ。`#` 始まりと空行は無視し、
    値を囲むクォートは剥がす。既存の `os.environ` は上書きしない。
    """
    path = DEFAULT_ENV_PATH if path is None else path
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


@dataclass(frozen=True)
class AttendanceConfig:
    """どのプロバイダーをどう起動するかの設定。"""

    provider: str
    base_url: str = ""
    login_id: str = ""
    password: str = ""
    #: プロバイダーのコンストラクタへ渡す追加引数。
    options: dict[str, Any] = field(default_factory=dict)

    def credentials(self) -> Credentials:
        return Credentials(login_id=self.login_id, password=self.password)

    def provider_kwargs(self) -> dict[str, Any]:
        """`registry.create()` に渡す引数を組み立てる。"""
        kwargs: dict[str, Any] = dict(self.options)
        if self.base_url:
            kwargs.setdefault("base_url", self.base_url)
        return kwargs


def load_config(
    path: Path | None = None,
    env: dict[str, str] | None = None,
    env_path: Path | None = None,
) -> AttendanceConfig:
    """設定ファイルと環境変数から設定を読む。

    環境変数はファイルの値より優先する（CI やタスクスケジューラーから
    資格情報だけを差し込めるようにするため）。
    優先順位は 実際の環境変数 > `.env` > 設定ファイル。
    """
    if env is None:
        env = {**load_dotenv(env_path), **os.environ}
    path = DEFAULT_CONFIG_PATH if path is None else path

    raw: dict[str, Any] = {}
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))

    provider = str(raw.get("provider", "")).strip()
    if not provider:
        raise ValueError(f"設定に provider がない: {path}")

    return AttendanceConfig(
        provider=provider,
        base_url=str(raw.get("base_url", "")),
        login_id=env.get(ENV_LOGIN_ID) or str(raw.get("login_id", "")),
        password=env.get(ENV_PASSWORD) or str(raw.get("password", "")),
        options=dict(raw.get("options", {})),
    )
