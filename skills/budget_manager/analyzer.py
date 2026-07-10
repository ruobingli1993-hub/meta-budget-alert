from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from config import ACCOUNT_CONFIGS, META_ACCESS_TOKEN
from feishu import FeishuWebhookClient
from meta_api import MetaAPIError, MetaMarketingAPI
from skills.budget_manager import rules


logger = logging.getLogger(__name__)

ACTION_TYPES = {
    "purchase": ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase", "onsite_conversion.purchase"),
    "purchase_value": ("purchase", "omni_purchase", "offsite_conversion.fb_pixel_purchase", "onsite_conversion.purchase"),
    "add_to_cart": ("add_to_cart", "omni_add_to_cart", "offsite_conversion.fb_pixel_add_to_cart"),
    "checkout": ("initiate_checkout", "omni_initiated_checkout", "offsite_conversion.fb_pixel_initiate_checkout"),
}


@dataclass
class BudgetRecommendation:
    account_name: str
    account_id: str
    account_regime: str
    account_3d_roas: str | None
    account_today_roas: str | None
    entity_level: str
    campaign_name: str
    campaign_id: str
    adset_name: str | None
    adset_id: str | None
    budget_model: str
    rtg: str
    delivery_status: str
    learning_status: str
    current_budget: str | None
    currency: str
    last_3d_spend: str
    last_3d_purchase: str
    last_3d_purchase_value: str
    last_3d_roas: str | None
    today_spend: str
    today_purchase: str
    today_purchase_value: str
    today_roas: str | None
    atc_rate: str
    checkout_rate: str
    funnel_anomaly: str
    data_confidence: str
    proposed_action: str
    proposed_new_budget: str | None
    adjustment_percentage: str
    reason: str
    optimization_hint: str


def preview() -> dict[str, Any]:
    config = rules.load_config()
    api = MetaMarketingAPI(META_ACCESS_TOKEN)
    run_id = "budget_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    recommendations: list[BudgetRecommendation] = []

    for account in ACCOUNT_CONFIGS:
        if account.account_type != config["performance_account_type"]:
            continue
        recommendations.extend(analyze_account(api, account, config))

    snapshot = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "recommendations": [asdict(item) for item in recommendations],
    }
    save_preview(snapshot, config)
    message = format_preview(snapshot)
    print(message)
    FeishuWebhookClient().send_text(message)
    return snapshot


def analyze_account(api: MetaMarketingAPI, account: Any, config: dict[str, Any]) -> list[BudgetRecommendation]:
    try:
        currency = get_account_currency(api, account)
        account_3d = get_metrics(api, account.api_id, "account", rules.date_ranges()["last_3_complete_days"])
        account_today = get_metrics(api, account.api_id, "account", rules.date_ranges()["today"])
        account_30d = get_metrics(api, account.api_id, "account", rules.date_ranges()["last_30_complete_days"])
        account_funnel, _ = rules.detect_funnel_anomaly(account_today, account_30d, config)
        account_regime, regime_reason = rules.determine_account_regime(account_3d, account_today, account_funnel, config)
        campaigns = get_campaigns(api, account)
        adsets = get_adsets(api, account)
    except Exception as exc:
        logger.error("Budget Manager account scan failed | account_id=%s | error=%s", account.account_id, sanitize_error(exc))
        return [data_error_recommendation(account, sanitize_error(exc))]

    recs: list[BudgetRecommendation] = []
    for campaign in campaigns:
        campaign_budget = parse_budget(campaign.get("daily_budget"), currency)
        has_campaign_budget = campaign_budget is not None or campaign.get("lifetime_budget")
        if has_campaign_budget:
            recs.append(analyze_entity(api, account, campaign, None, "Campaign", "CBO", currency, account_regime, account_3d, account_today, config))
            continue
        for adset in [row for row in adsets if row.get("campaign_id") == campaign.get("id") and row.get("daily_budget")]:
            recs.append(analyze_entity(api, account, campaign, adset, "Ad Set", "ABO", currency, account_regime, account_3d, account_today, config))
    if not recs:
        recs.append(data_error_recommendation(account, f"无法识别实际预算层级。Account regime: {account_regime}. {regime_reason}"))
    return recs


def analyze_entity(
    api: MetaMarketingAPI,
    account: Any,
    campaign: dict[str, Any],
    adset: dict[str, Any] | None,
    entity_level: str,
    budget_model: str,
    currency: str,
    account_regime: str,
    account_3d: rules.MetricWindow,
    account_today: rules.MetricWindow,
    config: dict[str, Any],
) -> BudgetRecommendation:
    entity_id = str(adset.get("id") if adset else campaign.get("id"))
    entity_name = str(adset.get("name") if adset else campaign.get("name"))
    level = "adset" if adset else "campaign"
    current_budget = parse_budget((adset or campaign).get("daily_budget"), currency)
    learning_status = extract_learning_status(adset)
    delivery_status = str((adset or campaign).get("effective_status") or "UNKNOWN")
    last_3d = get_metrics(api, entity_id, level, rules.date_ranges()["last_3_complete_days"])
    today = get_metrics(api, entity_id, level, rules.date_ranges()["today"])
    avg_30d = get_metrics(api, entity_id, level, rules.date_ranges()["last_30_complete_days"])
    rtg = rules.is_rtg(str(campaign.get("name") or ""), config)
    confidence = "HIGH" if rules.has_last_3d_sample(last_3d, config) and rules.has_today_sample(today, config) else "LOW"
    decision = rules.evaluate_entity(entity_level, budget_model, rtg, account_regime, last_3d, today, avg_30d, current_budget, learning_status, config)
    return BudgetRecommendation(
        account_name=account.name,
        account_id=account.account_id,
        account_regime=account_regime,
        account_3d_roas=fmt_optional(last_3d.roas),
        account_today_roas=fmt_optional(account_today.roas),
        entity_level=entity_level,
        campaign_name=str(campaign.get("name") or ""),
        campaign_id=str(campaign.get("id") or ""),
        adset_name=str(adset.get("name")) if adset else None,
        adset_id=str(adset.get("id")) if adset else None,
        budget_model=budget_model,
        rtg="Yes" if rtg else "No",
        delivery_status=delivery_status,
        learning_status=learning_status,
        current_budget=fmt_optional(current_budget),
        currency=currency,
        last_3d_spend=fmt_decimal(last_3d.spend),
        last_3d_purchase=fmt_decimal(last_3d.purchase),
        last_3d_purchase_value=fmt_decimal(last_3d.purchase_value),
        last_3d_roas=fmt_optional(last_3d.roas),
        today_spend=fmt_decimal(today.spend),
        today_purchase=fmt_decimal(today.purchase),
        today_purchase_value=fmt_decimal(today.purchase_value),
        today_roas=fmt_optional(today.roas),
        atc_rate=fmt_decimal(today.atc_rate),
        checkout_rate=fmt_decimal(today.checkout_rate),
        funnel_anomaly=decision["funnel_anomaly"],
        data_confidence=confidence,
        proposed_action=decision["proposed_action"],
        proposed_new_budget=decision["proposed_new_budget"],
        adjustment_percentage=decision["adjustment_percentage"],
        reason=decision["reason"],
        optimization_hint=decision["optimization_hint"],
    )


def get_account_currency(api: MetaMarketingAPI, account: Any) -> str:
    payload = api._request("GET", f"{api.base_url}/{account.api_id}", params={"fields": "currency", "access_token": api.access_token})
    currency = payload.get("currency")
    if not currency:
        raise RuntimeError("币种不明确")
    return str(currency)


def get_campaigns(api: MetaMarketingAPI, account: Any) -> list[dict[str, Any]]:
    payload = api._request("GET", f"{api.base_url}/{account.api_id}/campaigns", params={"fields": "id,name,effective_status,daily_budget,lifetime_budget", "limit": 200, "access_token": api.access_token})
    return [row for row in payload.get("data", []) if row.get("effective_status") == "ACTIVE"]


def get_adsets(api: MetaMarketingAPI, account: Any) -> list[dict[str, Any]]:
    payload = api._request("GET", f"{api.base_url}/{account.api_id}/adsets", params={"fields": "id,name,campaign_id,effective_status,daily_budget,lifetime_budget,learning_stage_info", "limit": 500, "access_token": api.access_token})
    return [row for row in payload.get("data", []) if row.get("effective_status") == "ACTIVE"]


def get_metrics(api: MetaMarketingAPI, object_id: str, level: str, time_range: dict[str, str]) -> rules.MetricWindow:
    payload = api._request(
        "GET",
        f"{api.base_url}/{object_id}/insights",
        params={
            "fields": "spend,actions,action_values,clicks,impressions",
            "time_range": json.dumps(time_range),
            "level": level,
            "access_token": api.access_token,
        },
    )
    rows = payload.get("data", [])
    if not rows:
        return rules.MetricWindow(Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
    return rows_to_metrics(rows)


def rows_to_metrics(rows: list[dict[str, Any]]) -> rules.MetricWindow:
    spend = Decimal("0")
    purchase = Decimal("0")
    purchase_value = Decimal("0")
    atc = Decimal("0")
    checkout = Decimal("0")
    clicks = Decimal("0")
    impressions = Decimal("0")
    for row in rows:
        if "spend" not in row:
            raise RuntimeError("Spend 缺失")
        spend += Decimal(str(row.get("spend") or "0"))
        clicks += Decimal(str(row.get("clicks") or "0"))
        impressions += Decimal(str(row.get("impressions") or "0"))
        purchase += action_value(row.get("actions", []), ACTION_TYPES["purchase"])
        purchase_value += action_value(row.get("action_values", []), ACTION_TYPES["purchase_value"])
        atc += action_value(row.get("actions", []), ACTION_TYPES["add_to_cart"])
        checkout += action_value(row.get("actions", []), ACTION_TYPES["checkout"])
    return rules.MetricWindow(spend, purchase, purchase_value, atc, checkout, clicks, impressions)


def action_value(actions: list[dict[str, Any]], action_types: tuple[str, ...]) -> Decimal:
    by_type = {str(row.get("action_type")): Decimal(str(row.get("value") or "0")) for row in actions}
    for action_type in action_types:
        if action_type in by_type:
            return by_type[action_type]
    return Decimal("0")


def parse_budget(raw_budget: Any, currency: str) -> Decimal | None:
    if raw_budget in (None, "", "0", 0):
        return None
    raw = Decimal(str(raw_budget))
    if currency.upper() in {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"}:
        return raw
    return (raw / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def extract_learning_status(adset: dict[str, Any] | None) -> str:
    if not adset:
        return "N/A"
    info = adset.get("learning_stage_info") or {}
    if isinstance(info, dict):
        return str(info.get("status") or info.get("phase") or "UNKNOWN")
    return "UNKNOWN"


def data_error_recommendation(account: Any, error: str) -> BudgetRecommendation:
    return BudgetRecommendation(
        account_name=account.name,
        account_id=account.account_id,
        account_regime="DATA_ERROR",
        account_3d_roas=None,
        account_today_roas=None,
        entity_level="Account",
        campaign_name="",
        campaign_id="",
        adset_name=None,
        adset_id=None,
        budget_model="UNKNOWN",
        rtg="No",
        delivery_status="UNKNOWN",
        learning_status="UNKNOWN",
        current_budget=None,
        currency="UNKNOWN",
        last_3d_spend="N/A",
        last_3d_purchase="N/A",
        last_3d_purchase_value="N/A",
        last_3d_roas=None,
        today_spend="N/A",
        today_purchase="N/A",
        today_purchase_value="N/A",
        today_roas=None,
        atc_rate="N/A",
        checkout_rate="N/A",
        funnel_anomaly="No",
        data_confidence="LOW",
        proposed_action="DATA_ERROR",
        proposed_new_budget=None,
        adjustment_percentage="0",
        reason=error,
        optimization_hint="Meta API 请求失败或关键数据缺失，不允许预算操作。",
    )


def fmt_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_optional(value: Decimal | None) -> str | None:
    return None if value is None else fmt_decimal(value)


def sanitize_error(exc: Exception) -> str:
    if isinstance(exc, MetaAPIError):
        return f"HTTP Status Code: {exc.http_status_code or 'unavailable'}; Meta Error Code: {exc.meta_error_code or 'unavailable'}; Error Message: {exc}"
    return type(exc).__name__


def save_preview(snapshot: dict[str, Any], config: dict[str, Any]) -> None:
    directory = Path(config["preview_log_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{snapshot['run_id']}.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def format_preview(snapshot: dict[str, Any]) -> str:
    lines = ["Budget Manager Preview", f"RUN_ID: {snapshot['run_id']}", "", "DEFAULT: NO ACTION until explicit APPLY.", ""]
    for item in snapshot["recommendations"]:
        lines.extend(format_recommendation(item))
    return "\n".join(lines)


def format_recommendation(item: dict[str, Any]) -> list[str]:
    return [
        "---",
        f"Account Name: {item['account_name']}",
        f"Account ID: {item['account_id']}",
        f"Account Regime: {item['account_regime']}",
        f"Account 3D ROAS: {item['account_3d_roas']}",
        f"Account Today ROAS: {item['account_today_roas']}",
        f"Entity Level: {item['entity_level']}",
        f"Campaign Name / ID: {item['campaign_name']} / {item['campaign_id']}",
        f"Ad Set Name / ID: {item['adset_name']} / {item['adset_id']}",
        f"ABO / CBO: {item['budget_model']}",
        f"RTG: {item['rtg']}",
        f"Delivery / Learning Status: {item['delivery_status']} / {item['learning_status']}",
        f"Current Budget: {item['current_budget']} {item['currency']}",
        f"Last 3 Complete Days Spend: {item['last_3d_spend']}",
        f"Last 3 Complete Days Purchase: {item['last_3d_purchase']}",
        f"Last 3 Complete Days Purchase Value: {item['last_3d_purchase_value']}",
        f"Last 3 Complete Days ROAS: {item['last_3d_roas']}",
        f"Today Spend: {item['today_spend']}",
        f"Today Purchase: {item['today_purchase']}",
        f"Today Purchase Value: {item['today_purchase_value']}",
        f"Today ROAS: {item['today_roas']}",
        f"ATC Rate: {item['atc_rate']}",
        f"Checkout Rate: {item['checkout_rate']}",
        f"Funnel Anomaly: {item['funnel_anomaly']}",
        f"Data Confidence: {item['data_confidence']}",
        f"Proposed Action: {item['proposed_action']}",
        f"Proposed New Budget: {item['proposed_new_budget']}",
        f"Adjustment Percentage: {item['adjustment_percentage']}",
        f"Reason: {item['reason']}",
        f"Optimization Hint: {item['optimization_hint']}",
    ]
