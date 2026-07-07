from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class AdAccount:
    name: str
    account_id: str

    @property
    def api_id(self) -> str:
        return f"act_{self.account_id}"


META_API_VERSION = os.getenv("META_API_VERSION", "v20.0")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")
DRY_RUN = os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes", "on"}

REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
REQUEST_MAX_RETRIES = int(os.getenv("REQUEST_MAX_RETRIES", "3"))
REQUEST_BACKOFF_SECONDS = float(os.getenv("REQUEST_BACKOFF_SECONDS", "2"))

STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))

ACCOUNTS: list[AdAccount] = [
    AdAccount(name="QMDT—20240103", account_id="750289240467952"),
    AdAccount(name="销售三部—新主页账户", account_id="5600626876733411"),
]


def validate_config() -> None:
    missing: list[str] = []
    if not META_ACCESS_TOKEN:
        missing.append("META_ACCESS_TOKEN")
    if not FEISHU_WEBHOOK_URL:
        missing.append("FEISHU_WEBHOOK_URL")

    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
