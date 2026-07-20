from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import AdAccount
from meta_api import MetaAPIError, MetaMarketingAPI


logger = logging.getLogger(__name__)
provider_logger = logging.getLogger("meta_data_provider")

META_DATA_PROVIDER_LOG = Path("logs/meta_data_provider.log")
ZERO = Decimal("0")
ZERO_DECIMAL_CURRENCIES = {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}

DataStatus = Literal["SUCCESS", "EMPTY", "ERROR"]
InsightLevel = Literal["account", "campaign", "adset"]

INSIGHT_FIELDS = "spend,actions,action_values,purchase_roas,clicks,inline_link_clicks,impressions,reach"
CAMPAIGN_INSIGHT_FIELDS = "campaign_id,campaign_name," + INSIGHT_FIELDS
ADSET_INSIGHT_FIELDS = "campaign_id,campaign_name,adset_id,adset_name," + INSIGHT_FIELDS

PURCHASE_ACTION_TYPES = ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase")
PURCHASE_VALUE_ACTION_TYPES = PURCHASE_ACTION_TYPES
PURCHASE_ROAS_ACTION_TYPES = ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase")
ATC_ACTION_TYPES = ("add_to_cart", "offsite_conversion.fb_pixel_add_to_cart", "omni_add_to_cart")
CHECKOUT_ACTION_TYPES = ("initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout", "omni_initiated_checkout")
LINK_CLICK_ACTION_TYPES = ("link_click",)


@dataclass(frozen=True)
class AccountMeta:
    account_id: str
    account_name: str
    api_id: str
    currency: str
    timezone_name: str
    timezone_offset_hours_utc: str | None
    account_today: date


@dataclass(frozen=True)
class PeriodSpec:
    period: str
    since: str
    until: str
    date_preset: str | None = None
    includes_today: bool = False


@dataclass(frozen=True)
class SelectedAction:
    action_type: str | None
    value: Decimal | None


@dataclass(frozen=True)
class InsightRecord:
    account_id: str
    account_name: str
    timezone: str
    timezone_offset_hours_utc: str | None
    currency: str
    level: InsightLevel
    entity_id: str
    entity_name: str
    period: str
    since: str
    until: str
    date_preset: str | None
    spend: Decimal | None
    purchase: Decimal | None
    purchase_value: Decimal | None
    roas: Decimal | None
    impressions: Decimal | None
    clicks: Decimal | None
    link_clicks: Decimal | None
    reach: Decimal | None
    ctr: Decimal | None
    frequency: Decimal | None
    add_to_cart: Decimal | None
    checkout: Decimal | None
    data_status: DataStatus
    error: str | None = None
    http_status_code: int | None = None
    meta_error_code: int | str | None = None
    raw_action_types: tuple[str, ...] = ()
    raw_action_value_types: tuple[str, ...] = ()
    raw_purchase_roas_types: tuple[str, ...] = ()
    selected_purchase_action_type: str | None = None
    selected_purchase_value_action_type: str | None = None
    raw_spend: str | None = None
    raw_rows_sample: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class EntityInfo:
    account_id: str
    account_name: str
    level: Literal["campaign", "adset"]
    entity_id: str
    entity_name: str
    campaign_id: str | None
    campaign_name: str | None
    effective_status: str
    daily_budget: Decimal | None
    lifetime_budget: Decimal | None
    currency: str
    learning_status: str


class MetaDataProvider:
    def __init__(self, api: MetaMarketingAPI) -> None:
        self.api = api

    def get_account_meta(self, account: AdAccount) -> AccountMeta:
        payload = self.api._request(
            "GET",
            f"{self.api.base_url}/{account.api_id}",
            params={
                "fields": "currency,timezone_name,timezone_offset_hours_utc",
                "access_token": self.api.access_token,
            },
        )
        currency = str(payload.get("currency") or "USD")
        timezone_name = str(payload.get("timezone_name") or "UTC")
        return AccountMeta(
            account_id=account.account_id,
            account_name=account.name,
            api_id=account.api_id,
            currency=currency,
            timezone_name=timezone_name,
            timezone_offset_hours_utc=str(payload.get("timezone_offset_hours_utc")) if payload.get("timezone_offset_hours_utc") is not None else None,
            account_today=account_today(timezone_name),
        )

    def period(self, meta: AccountMeta, name: str) -> PeriodSpec:
        current = meta.account_today
        if name == "today":
            return PeriodSpec(period="today", since=current.isoformat(), until=current.isoformat(), date_preset="today", includes_today=True)
        if name == "last_3_complete_days":
            return PeriodSpec(period=name, since=(current - timedelta(days=3)).isoformat(), until=(current - timedelta(days=1)).isoformat())
        if name == "last_7_complete_days":
            return PeriodSpec(period=name, since=(current - timedelta(days=7)).isoformat(), until=(current - timedelta(days=1)).isoformat())
        if name == "last_30_complete_days":
            return PeriodSpec(period=name, since=(current - timedelta(days=30)).isoformat(), until=(current - timedelta(days=1)).isoformat())
        raise ValueError(f"Unsupported period: {name}")

    def get_insights(
        self,
        account: AdAccount,
        level: InsightLevel,
        period_name: str,
        entity_id: str | None = None,
        entity_name: str | None = None,
        meta: AccountMeta | None = None,
    ) -> list[InsightRecord]:
        account_meta = meta or self.get_account_meta(account)
        period = self.period(account_meta, period_name)
        return self.get_insights_for_period(account, level, period, entity_id=entity_id, entity_name=entity_name, meta=account_meta)

    def get_insights_for_period(
        self,
        account: AdAccount,
        level: InsightLevel,
        period: PeriodSpec,
        entity_id: str | None = None,
        entity_name: str | None = None,
        meta: AccountMeta | None = None,
        hourly_until_hour: int | None = None,
    ) -> list[InsightRecord]:
        account_meta = meta or self.get_account_meta(account)
        object_id = entity_id or account.api_id
        fields = insight_fields(level)
        params: dict[str, Any] = {"fields": fields, "access_token": self.api.access_token}
        if level != "account":
            params["level"] = level
            params["limit"] = 500
        if period.date_preset:
            params["date_preset"] = period.date_preset
        else:
            params["time_range"] = json.dumps({"since": period.since, "until": period.until})
        if hourly_until_hour is not None:
            params["breakdowns"] = "hourly_stats_aggregated_by_advertiser_time_zone"

        try:
            payload = self.api._request("GET", f"{self.api.base_url}/{object_id}/insights", params=params)
        except MetaAPIError as exc:
            record = error_record(account_meta, level, object_id, entity_name or object_id, period, fields, exc)
            write_provider_log(record, fields)
            return [record]

        rows = list(payload.get("data", []))
        if hourly_until_hour is not None:
            rows = [row for row in rows if hourly_row_start(row) is None or hourly_row_start(row) <= hourly_until_hour]
        if not rows:
            record = empty_record(account_meta, level, object_id, entity_name or object_id, period)
            write_provider_log(record, fields)
            return [record]

        records = [record_from_row(account_meta, level, period, row, object_id, entity_name) for row in rows]
        for record in records:
            write_provider_log(record, fields)
        return records

    def get_campaigns(self, account: AdAccount, meta: AccountMeta | None = None) -> list[EntityInfo]:
        account_meta = meta or self.get_account_meta(account)
        payload = self.api._request(
            "GET",
            f"{self.api.base_url}/{account.api_id}/campaigns",
            params={"fields": "id,name,effective_status,daily_budget,lifetime_budget", "limit": 500, "access_token": self.api.access_token},
        )
        return [
            EntityInfo(
                account_id=account.account_id,
                account_name=account.name,
                level="campaign",
                entity_id=str(row.get("id") or ""),
                entity_name=str(row.get("name") or ""),
                campaign_id=str(row.get("id") or ""),
                campaign_name=str(row.get("name") or ""),
                effective_status=str(row.get("effective_status") or "N/A"),
                daily_budget=parse_budget(row.get("daily_budget"), account_meta.currency),
                lifetime_budget=parse_budget(row.get("lifetime_budget"), account_meta.currency),
                currency=account_meta.currency,
                learning_status="N/A",
            )
            for row in payload.get("data", [])
        ]

    def get_adsets(self, account: AdAccount, meta: AccountMeta | None = None) -> list[EntityInfo]:
        account_meta = meta or self.get_account_meta(account)
        payload = self.api._request(
            "GET",
            f"{self.api.base_url}/{account.api_id}/adsets",
            params={
                "fields": "id,name,campaign_id,campaign{name},effective_status,daily_budget,lifetime_budget,learning_stage_info",
                "limit": 500,
                "access_token": self.api.access_token,
            },
        )
        adsets: list[EntityInfo] = []
        for row in payload.get("data", []):
            campaign = row.get("campaign") if isinstance(row.get("campaign"), dict) else {}
            adsets.append(
                EntityInfo(
                    account_id=account.account_id,
                    account_name=account.name,
                    level="adset",
                    entity_id=str(row.get("id") or ""),
                    entity_name=str(row.get("name") or ""),
                    campaign_id=str(row.get("campaign_id") or campaign.get("id") or ""),
                    campaign_name=str(campaign.get("name") or ""),
                    effective_status=str(row.get("effective_status") or "N/A"),
                    daily_budget=parse_budget(row.get("daily_budget"), account_meta.currency),
                    lifetime_budget=parse_budget(row.get("lifetime_budget"), account_meta.currency),
                    currency=account_meta.currency,
                    learning_status=extract_learning_status(row),
                )
            )
        return adsets


def account_today(timezone_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        return datetime.utcnow().date()


def insight_fields(level: InsightLevel) -> str:
    if level == "campaign":
        return CAMPAIGN_INSIGHT_FIELDS
    if level == "adset":
        return ADSET_INSIGHT_FIELDS
    return INSIGHT_FIELDS


def hourly_row_start(row: dict[str, Any]) -> int | None:
    raw = row.get("hourly_stats_aggregated_by_advertiser_time_zone")
    if not raw:
        return None
    text = str(raw).split(" - ")[0]
    try:
        return int(text.split(":")[0])
    except (ValueError, IndexError):
        return None


def record_from_row(account: AccountMeta, level: InsightLevel, period: PeriodSpec, row: dict[str, Any], fallback_id: str, fallback_name: str | None) -> InsightRecord:
    spend = decimal_or_none(row.get("spend"))
    impressions = decimal_or_none(row.get("impressions"))
    clicks = decimal_or_none(row.get("clicks"))
    inline_link_clicks = decimal_or_none(row.get("inline_link_clicks"))
    link_click_action = select_action(row.get("actions", []), LINK_CLICK_ACTION_TYPES)
    link_clicks = link_click_action.value if link_click_action.value is not None else inline_link_clicks
    reach = decimal_or_none(row.get("reach"))
    purchase = select_action(row.get("actions", []), PURCHASE_ACTION_TYPES)
    purchase_value = select_action(row.get("action_values", []), PURCHASE_VALUE_ACTION_TYPES)
    purchase_roas = select_action(row.get("purchase_roas", []), PURCHASE_ROAS_ACTION_TYPES)
    add_to_cart = select_action(row.get("actions", []), ATC_ACTION_TYPES)
    checkout = select_action(row.get("actions", []), CHECKOUT_ACTION_TYPES)
    # The report contract requires ROAS = Purchase Value / Spend. Meta's native
    # purchase_roas is retained only as source diagnostics and must not be used
    # to fabricate a missing Purchase Value.
    roas = safe_div_optional(purchase_value.value, spend)
    entity_id = str(row.get(f"{level}_id") or fallback_id)
    entity_name = str(row.get(f"{level}_name") or fallback_name or entity_id)
    if level == "account":
        entity_id = account.account_id
        entity_name = account.account_name

    return InsightRecord(
        account_id=account.account_id,
        account_name=account.account_name,
        timezone=account.timezone_name,
        timezone_offset_hours_utc=account.timezone_offset_hours_utc,
        currency=account.currency,
        level=level,
        entity_id=entity_id,
        entity_name=entity_name,
        period=period.period,
        since=period.since,
        until=period.until,
        date_preset=period.date_preset,
        spend=spend,
        purchase=purchase.value,
        purchase_value=purchase_value.value,
        roas=roas,
        impressions=impressions,
        clicks=clicks,
        link_clicks=link_clicks,
        reach=reach,
        ctr=safe_div_optional(clicks, impressions),
        frequency=safe_div_optional(impressions, reach),
        add_to_cart=add_to_cart.value,
        checkout=checkout.value,
        data_status="SUCCESS",
        raw_action_types=action_types(row.get("actions", [])),
        raw_action_value_types=action_types(row.get("action_values", [])),
        raw_purchase_roas_types=action_types(row.get("purchase_roas", [])),
        selected_purchase_action_type=purchase.action_type,
        selected_purchase_value_action_type=purchase_value.action_type,
        raw_spend=str(row.get("spend")) if row.get("spend") is not None else None,
        raw_rows_sample=(row,),
    )


def empty_record(account: AccountMeta, level: InsightLevel, entity_id: str, entity_name: str, period: PeriodSpec) -> InsightRecord:
    return InsightRecord(
        account_id=account.account_id,
        account_name=account.account_name,
        timezone=account.timezone_name,
        timezone_offset_hours_utc=account.timezone_offset_hours_utc,
        currency=account.currency,
        level=level,
        entity_id=entity_id.replace("act_", ""),
        entity_name=entity_name,
        period=period.period,
        since=period.since,
        until=period.until,
        date_preset=period.date_preset,
        spend=ZERO,
        purchase=ZERO,
        purchase_value=None,
        roas=None,
        impressions=ZERO,
        clicks=ZERO,
        link_clicks=ZERO,
        reach=ZERO,
        ctr=None,
        frequency=None,
        add_to_cart=ZERO,
        checkout=ZERO,
        data_status="EMPTY",
        error="Meta API returned no insight rows for this period.",
        raw_spend="0",
    )


def error_record(account: AccountMeta, level: InsightLevel, entity_id: str, entity_name: str, period: PeriodSpec, fields: str, exc: MetaAPIError) -> InsightRecord:
    return InsightRecord(
        account_id=account.account_id,
        account_name=account.account_name,
        timezone=account.timezone_name,
        timezone_offset_hours_utc=account.timezone_offset_hours_utc,
        currency=account.currency,
        level=level,
        entity_id=entity_id.replace("act_", ""),
        entity_name=entity_name,
        period=period.period,
        since=period.since,
        until=period.until,
        date_preset=period.date_preset,
        spend=None,
        purchase=None,
        purchase_value=None,
        roas=None,
        impressions=None,
        clicks=None,
        link_clicks=None,
        reach=None,
        ctr=None,
        frequency=None,
        add_to_cart=None,
        checkout=None,
        data_status="ERROR",
        error=str(exc),
        http_status_code=exc.http_status_code,
        meta_error_code=exc.meta_error_code,
    )


def select_action(actions: list[dict[str, Any]], candidates: tuple[str, ...]) -> SelectedAction:
    by_type: dict[str, Decimal] = {}
    for row in actions or []:
        action_type = str(row.get("action_type") or "")
        if action_type and action_type not in by_type:
            value = decimal_or_none(row.get("value"))
            if value is not None:
                by_type[action_type] = value
    for candidate in candidates:
        if candidate in by_type:
            return SelectedAction(candidate, by_type[candidate])
    return SelectedAction(None, None)


def action_types(actions: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(str(row.get("action_type") or "") for row in actions or [] if row.get("action_type"))


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def safe_div_optional(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else ZERO


def sum_records(records: list[InsightRecord], level: InsightLevel, period: str) -> InsightRecord:
    if not records:
        raise ValueError("Cannot sum empty insight record list.")
    first = records[0]
    non_success = [record for record in records if record.data_status != "SUCCESS"]
    if non_success:
        return non_success[0]
    spend = sum((decimal_or_zero(record.spend) for record in records), ZERO)
    purchase = sum((decimal_or_zero(record.purchase) for record in records), ZERO)
    purchase_values = [record.purchase_value for record in records]
    purchase_value = None if any(value is None for value in purchase_values) else sum((decimal_or_zero(value) for value in purchase_values), ZERO)
    impressions = sum((decimal_or_zero(record.impressions) for record in records), ZERO)
    clicks = sum((decimal_or_zero(record.clicks) for record in records), ZERO)
    link_clicks = sum((decimal_or_zero(record.link_clicks) for record in records), ZERO)
    reach = sum((decimal_or_zero(record.reach) for record in records), ZERO)
    add_to_cart = sum((decimal_or_zero(record.add_to_cart) for record in records), ZERO)
    checkout = sum((decimal_or_zero(record.checkout) for record in records), ZERO)
    return InsightRecord(
        account_id=first.account_id,
        account_name=first.account_name,
        timezone=first.timezone,
        timezone_offset_hours_utc=first.timezone_offset_hours_utc,
        currency=first.currency,
        level=level,
        entity_id=first.account_id if level == "account" else "combined",
        entity_name=first.account_name if level == "account" else "Combined",
        period=period,
        since=first.since,
        until=first.until,
        date_preset=first.date_preset,
        spend=spend,
        purchase=purchase,
        purchase_value=purchase_value,
        roas=safe_div_optional(purchase_value, spend),
        impressions=impressions,
        clicks=clicks,
        link_clicks=link_clicks,
        reach=reach,
        ctr=safe_div_optional(clicks, impressions),
        frequency=safe_div_optional(impressions, reach),
        add_to_cart=add_to_cart,
        checkout=checkout,
        data_status="SUCCESS",
    )


def parse_budget(raw_budget: Any, currency: str) -> Decimal | None:
    if raw_budget in (None, "", "0", 0):
        return None
    raw = Decimal(str(raw_budget))
    if currency.upper() in ZERO_DECIMAL_CURRENCIES:
        return raw
    return raw / Decimal("100")


def extract_learning_status(row: dict[str, Any]) -> str:
    info = row.get("learning_stage_info") or {}
    if not isinstance(info, dict):
        return "N/A"
    raw_status = str(info.get("status") or info.get("phase") or info.get("learning_stage") or "").strip()
    normalized = raw_status.replace("_", " ").upper()
    if normalized in {"LEARNING", "LEARNING LIMITED"}:
        return normalized.title()
    return "N/A"


def write_provider_log(record: InsightRecord, fields: str) -> None:
    payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "account_id": record.account_id,
        "account_name": record.account_name,
        "level": record.level,
        "entity_id": record.entity_id,
        "period": record.period,
        "timezone": record.timezone,
        "timezone_offset_hours_utc": record.timezone_offset_hours_utc,
        "since": record.since,
        "until": record.until,
        "date_preset": record.date_preset,
        "requested_fields": fields,
        "response_has_data": "yes" if record.data_status == "SUCCESS" else "no",
        "raw_spend": record.raw_spend,
        "raw_actions_action_type_list": list(record.raw_action_types),
        "raw_action_values_action_type_list": list(record.raw_action_value_types),
        "raw_purchase_roas_action_type_list": list(record.raw_purchase_roas_types),
        "selected_purchase_action_type": record.selected_purchase_action_type,
        "selected_purchase_value_action_type": record.selected_purchase_value_action_type,
        "parsed_purchase": str(record.purchase) if record.purchase is not None else None,
        "parsed_purchase_value": str(record.purchase_value) if record.purchase_value is not None else None,
        "parsed_roas": str(record.roas) if record.roas is not None else None,
        "data_status": record.data_status,
        "http_status_code": record.http_status_code,
        "meta_error_code": record.meta_error_code,
        "error": record.error,
    }
    META_DATA_PROVIDER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with META_DATA_PROVIDER_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    provider_logger.info(
        "Meta Data Provider | account_id=%s | level=%s | entity_id=%s | period=%s | status=%s | raw_spend=%s | purchase=%s | purchase_value=%s | roas=%s",
        record.account_id,
        record.level,
        record.entity_id,
        record.period,
        record.data_status,
        record.raw_spend,
        record.purchase,
        record.purchase_value,
        record.roas,
    )
