from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

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

    @property
    def should_alert(self) -> bool:
        return self.current_balance < self.threshold


class MetaMarketingAPI:
    def __init__(self, access_token: str = META_ACCESS_TOKEN) -> None:
        self.access_token = access_token
        self.base_url = f"https://graph.facebook.com/{META_API_VERSION}"
        self.session = requests.Session()

    def get_budget_snapshot(self, account: AdAccount) -> AccountBudgetSnapshot:
        account_info = self._get_account_info(account)
        currency = str(account_info.get("currency") or "USD")
        balance = self._parse_account_money(account_info.get("balance"), currency)
        seven_day_spend = self._get_last_7_days_spend(account)
        average_daily_spend = seven_day_spend / Decimal("7")
        threshold = average_daily_spend * Decimal("3")

        return AccountBudgetSnapshot(
            account=account,
            currency=currency,
            seven_day_spend=seven_day_spend,
            average_daily_spend=average_daily_spend,
            current_balance=balance,
            threshold=threshold,
        )

    def get_account_balance(self, account: AdAccount) -> tuple[Decimal, str]:
        account_info = self._get_account_info(account)
        currency = str(account_info.get("currency") or "USD")
        return self._parse_account_money(account_info.get("balance"), currency), currency

    def get_spend_limit_balance(self, account: AdAccount) -> tuple[Decimal | None, str]:
        account_info = self._request(
            "GET",
            f"{self.base_url}/{account.api_id}",
            params={
                "fields": "account_spend_limit,amount_spent,currency",
                "access_token": self.access_token,
            },
        )
        currency = str(account_info.get("currency") or "USD")
        raw_limit = account_info.get("account_spend_limit")
        if raw_limit in (None, "", "0", 0):
            return None, currency

        spend_limit = self._parse_account_money(raw_limit, currency)
        amount_spent = self._parse_account_money(account_info.get("amount_spent"), currency)
        available = spend_limit - amount_spent
        return max(available, Decimal("0")), currency

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

    def _get_last_7_days_spend(self, account: AdAccount) -> Decimal:
        response = self._request(
            "GET",
            f"{self.base_url}/{account.api_id}/insights",
            params={
                "fields": "spend",
                "date_preset": "last_7d",
                "access_token": self.access_token,
            },
        )

        rows = response.get("data", [])
        if not rows:
            return Decimal("0")

        total = Decimal("0")
        for row in rows:
            total += self._decimal(row.get("spend", "0"))
        return total

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
