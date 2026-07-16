from __future__ import annotations

import logging
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests

from config import (
    META_ACCESS_TOKEN,
    META_API_VERSION,
    REQUEST_BACKOFF_SECONDS,
    REQUEST_MAX_RETRIES,
    REQUEST_TIMEOUT_SECONDS,
    AdAccount,
)


logger = logging.getLogger(__name__)


class MetaAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        http_status_code: int | None = None,
        meta_error_code: int | str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status_code = http_status_code
        self.meta_error_code = meta_error_code


@dataclass(frozen=True)
class AccountBudgetSnapshot:
    account: AdAccount
    currency: str
    seven_day_spend: Decimal
    average_daily_spend: Decimal
    current_balance: Decimal
    threshold: Decimal
    account_spend_limit: Decimal
    amount_spent: Decimal
    account_status: str = "unknown"
    account_timezone: str = "UTC"
    last_7_complete_days_range: dict[str, str] | None = None
    balance_source: str = "spend_cap - amount_spent"
    threshold_days: Decimal = Decimal("3")

    @property
    def should_alert(self) -> bool:
        return self.trigger_by_amount

    @property
    def trigger_by_amount(self) -> bool:
        return self.current_balance <= self.threshold

    @property
    def trigger_by_days(self) -> bool:
        if self.estimated_days_remaining is None:
            return False
        return self.estimated_days_remaining <= self.threshold_days

    @property
    def estimated_days_remaining(self) -> Decimal | None:
        if self.average_daily_spend <= 0:
            return None
        return self.current_balance / self.average_daily_spend


class MetaMarketingAPI:
    def __init__(self, access_token: str = META_ACCESS_TOKEN) -> None:
        self.access_token = access_token
        self.base_url = f"https://graph.facebook.com/{META_API_VERSION}"
        self.session = requests.Session()

    def get_budget_snapshot(self, account: AdAccount) -> AccountBudgetSnapshot:
        account_info = self._get_spend_limit_info(account)
        currency = str(account_info.get("currency") or "USD")
        raw_limit = account_info.get("spend_cap")
        if raw_limit in (None, "", "0", 0):
            raise MetaAPIError(
                f"Spend cap is unavailable for {account.name}; refusing to use the legacy balance field"
            )
        spend_limit = self._parse_account_money(raw_limit, currency)
        amount_spent = self._parse_account_money(account_info.get("amount_spent"), currency)
        balance = max(spend_limit - amount_spent, Decimal("0"))
        last_7_range = self._last_7_complete_days_range(account_info)
        seven_day_spend = self._get_last_7_complete_days_spend(account, account_info)
        average_daily_spend = seven_day_spend / Decimal("7")
        threshold = average_daily_spend * Decimal("3")

        return AccountBudgetSnapshot(
            account=account,
            currency=currency,
            seven_day_spend=seven_day_spend,
            average_daily_spend=average_daily_spend,
            current_balance=balance,
            threshold=threshold,
            account_spend_limit=spend_limit,
            amount_spent=amount_spent,
            account_status=str(account_info.get("account_status") or "unknown"),
            account_timezone=str(account_info.get("timezone_name") or "UTC"),
            last_7_complete_days_range=last_7_range,
        )

    def get_account_balance(self, account: AdAccount) -> tuple[Decimal, str]:
        account_info = self._get_account_info(account)
        currency = str(account_info.get("currency") or "USD")
        return self._parse_account_money(account_info.get("balance"), currency), currency

    def get_spend_limit_balance(self, account: AdAccount) -> tuple[Decimal | None, str]:
        account_info = self._get_spend_limit_info(account)
        currency = str(account_info.get("currency") or "USD")
        raw_limit = account_info.get("spend_cap")
        if raw_limit in (None, "", "0", 0):
            return None, currency

        spend_limit = self._parse_account_money(raw_limit, currency)
        amount_spent = self._parse_account_money(account_info.get("amount_spent"), currency)
        available = spend_limit - amount_spent
        return max(available, Decimal("0")), currency

    def _get_spend_limit_info(self, account: AdAccount) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.base_url}/{account.api_id}",
            params={
                "fields": "spend_cap,amount_spent,currency,account_status,timezone_name",
                "access_token": self.access_token,
            },
        )

    def get_account_insights(self, account: AdAccount, date_preset: str) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"{self.base_url}/{account.api_id}/insights",
            params={
                "fields": "spend,actions,action_values,clicks,impressions,reach",
                "date_preset": date_preset,
                "access_token": self.access_token,
            },
        )
        return list(response.get("data", []))

    def get_campaign_insights(
        self,
        account: AdAccount,
        date_preset: str = "today",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        response = self._request(
            "GET",
            f"{self.base_url}/{account.api_id}/insights",
            params={
                "fields": "campaign_id,campaign_name,spend,actions,action_values,clicks,impressions,reach",
                "date_preset": date_preset,
                "level": "campaign",
                "limit": limit,
                "access_token": self.access_token,
            },
        )
        return list(response.get("data", []))

    def _get_account_info(self, account: AdAccount) -> dict[str, Any]:
        return self._request(
            "GET",
            f"{self.base_url}/{account.api_id}",
            params={
                "fields": "balance,currency,account_status",
                "access_token": self.access_token,
            },
        )

    def _get_last_7_complete_days_spend(self, account: AdAccount, account_info: dict[str, Any]) -> Decimal:
        time_range = self._last_7_complete_days_range(account_info)
        response = self._request(
            "GET",
            f"{self.base_url}/{account.api_id}/insights",
            params={
                "fields": "spend",
                "time_range": json.dumps(time_range),
                "access_token": self.access_token,
            },
        )

        rows = response.get("data", [])
        if not rows:
            raise MetaAPIError(f"Meta API returned no last 7 complete days spend rows for {account.name}")

        total = Decimal("0")
        for row in rows:
            total += self._decimal(row.get("spend", "0"))
        return total

    def _last_7_complete_days_range(self, account_info: dict[str, Any]) -> dict[str, str]:
        today = self._account_today(account_info.get("timezone_name"))
        return {
            "since": (today - timedelta(days=7)).isoformat(),
            "until": (today - timedelta(days=1)).isoformat(),
        }

    def _get_last_7_days_spend(self, account: AdAccount) -> Decimal:
        return self._get_last_7_complete_days_spend(account, self._get_spend_limit_info(account))

    @staticmethod
    def _account_today(timezone_name: Any) -> date:
        try:
            return datetime.now(ZoneInfo(str(timezone_name or "UTC"))).date()
        except ZoneInfoNotFoundError:
            return datetime.utcnow().date()

    def _request(self, method: str, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(1, REQUEST_MAX_RETRIES + 1):
            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                payload = response.json()

                if response.status_code >= 500 or response.status_code == 429:
                    error = payload.get("error", {}) if isinstance(payload, dict) else {}
                    raise MetaAPIError(
                        error.get("message", "Meta API temporary error"),
                        http_status_code=response.status_code,
                        meta_error_code=error.get("code"),
                    )

                if response.status_code >= 400 or "error" in payload:
                    error = payload.get("error", {}) if isinstance(payload, dict) else {}
                    raise MetaAPIError(
                        error.get("message", "Meta API error"),
                        http_status_code=response.status_code,
                        meta_error_code=error.get("code"),
                    )

                return payload
            except (requests.RequestException, ValueError, MetaAPIError) as exc:
                last_error = exc
                if attempt == REQUEST_MAX_RETRIES:
                    break

                sleep_seconds = REQUEST_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Meta API request failed on attempt %s/%s. Retrying in %.1fs.",
                    attempt,
                    REQUEST_MAX_RETRIES,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        if isinstance(last_error, MetaAPIError):
            raise last_error

        error_name = type(last_error).__name__ if last_error else "UnknownError"
        raise MetaAPIError(f"Meta API request failed after retries: {error_name}") from last_error

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError) as exc:
            raise MetaAPIError(f"Invalid money value from Meta API: {value}") from exc

    def _parse_account_money(self, value: Any, currency: str) -> Decimal:
        raw = self._decimal(value or "0")
        if currency.upper() in {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}:
            return raw
        return raw / Decimal("100")
