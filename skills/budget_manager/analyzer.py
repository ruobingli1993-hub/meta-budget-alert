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
from meta_data_provider import EntityInfo, InsightRecord, MetaDataProvider, decimal_or_zero
from skills.budget_manager import audit
from skills.budget_manager import rules


logger = logging.getLogger(__name__)
ZERO = Decimal("0")


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
    account_regime_reason: str = ""
    matched_rule: str = ""
    cooldown_status: str = "CLEAR"
    api_result: str = "SUCCESS"
    account_timezone: str = "unknown"
    today_request_since: str = ""
    today_request_until: str = ""
    today_date_preset: str = ""
    today_raw_has_data: str = "No"
    today_raw_spend: str = "N/A"
    today_raw_actions: list[dict[str, Any]] | None = None
    today_raw_action_values: list[dict[str, Any]] | None = None
    today_raw_data: list[dict[str, Any]] | None = None
    parsed_today_purchase: str = "N/A"
    parsed_today_atc: str = "N/A"
    parsed_today_checkout: str = "N/A"
    parsed_today_link_clicks: str = "N/A"
    regime_calculation_inputs: dict[str, Any] | None = None


def preview() -> dict[str, Any]:
    print("Budget Manager Started")
    print("Loading configuration...")
    config = rules.load_config()
    api = MetaMarketingAPI(META_ACCESS_TOKEN)
    provider = MetaDataProvider(api)
    run_id = "budget_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    start_time = datetime.now().isoformat(timespec="seconds")
    recommendations: list[BudgetRecommendation] = []
    target_accounts = [account.account_id for account in ACCOUNT_CONFIGS if account.account_type == config["performance_account_type"]]
    audit.append_log(config, {**audit.run_base(run_id, "preview", start_time, config, target_accounts), "event": "START"})

    performance_accounts = [account for account in ACCOUNT_CONFIGS if account.account_type == config["performance_account_type"]]
    for index, account in enumerate(performance_accounts, start=1):
        print(f"Processing Account {index}/{len(performance_accounts)}...")
        recs = analyze_account(provider, account, config, run_id)
        recommendations.extend(recs)
        for rec in recs:
            audit.append_log(config, {"run_id": run_id, "mode": "preview", "event": "SCAN_RESULT", **asdict(rec)})

    snapshot = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "recommendations": [asdict(item) for item in recommendations],
    }
    save_preview(snapshot, config)
    print("Preview generated...")
    message = format_preview(snapshot)
    print(message)
    errors: list[str] = []
    status = audit.overall_status(snapshot["recommendations"])
    try:
        FeishuWebhookClient().send_text(message)
        print("Feishu preview sent...")
    except Exception as exc:
        status = "FAILED"
        errors.append(type(exc).__name__)
        audit.append_log(config, {"run_id": run_id, "mode": "preview", "event": "FEISHU_ERROR", "error": type(exc).__name__})
        raise
    finally:
        end_time = datetime.now().isoformat(timespec="seconds")
        report_path = audit.save_run_report(config, run_id, "preview", start_time, end_time, status, snapshot["recommendations"], errors)
        audit.append_log(config, {"run_id": run_id, "mode": "preview", "event": "END", "end_time": end_time, "overall_status": status, "run_report": str(report_path)})
        print(f"Run report saved to: {report_path}")
        print(f"Overall Status: {status}")
    return snapshot


def analyze_account(provider: MetaDataProvider, account: Any, config: dict[str, Any], run_id: str | None = None) -> list[BudgetRecommendation]:
    try:
        meta = provider.get_account_meta(account)
        account_3d = provider.get_insights(account, "account", "last_3_complete_days", meta=meta)[0]
        account_today = provider.get_insights(account, "account", "today", meta=meta)[0]
        account_30d = provider.get_insights(account, "account", "last_30_complete_days", meta=meta)[0]
        account_3d_window = metric_window(account_3d)
        account_today_window = metric_window(account_today)
        account_30d_window = metric_window(account_30d)

        account_funnel, _ = rules.detect_funnel_anomaly(account_today_window, account_30d_window, config)
        account_regime, regime_reason = account_regime_from_records(account_3d, account_today, account_3d_window, account_today_window, account_funnel, config)
        regime_inputs = regime_debug(account_3d, account_today, account_regime, regime_reason)
        print_regime_debug(account.account_id, regime_inputs)
        if run_id:
            audit.append_log(config, {"run_id": run_id, "mode": "preview", "event": "ACCOUNT_REGIME", **regime_inputs})
        print("Scanning Campaigns...")
        campaigns = [item for item in provider.get_campaigns(account, meta=meta) if item.effective_status == "ACTIVE"]
        print("Scanning Ad Sets...")
        adsets = [item for item in provider.get_adsets(account, meta=meta) if item.effective_status == "ACTIVE"]
    except Exception as exc:
        clean_error = sanitize_error(exc)
        logger.error("Budget Manager account scan failed | account_id=%s | error=%s", account.account_id, clean_error)
        return [data_error_recommendation(account, clean_error)]

    recs: list[BudgetRecommendation] = []
    print("Evaluating rules...")
    for campaign in campaigns:
        has_campaign_budget = campaign.daily_budget is not None or campaign.lifetime_budget is not None
        if has_campaign_budget:
            recs.append(analyze_entity(provider, account, campaign, None, "Campaign", "CBO", account_regime, regime_reason, account_3d_window, account_today, regime_inputs, config))
            continue
        campaign_adsets = [row for row in adsets if row.campaign_id == campaign.entity_id and row.daily_budget is not None]
        for adset in campaign_adsets:
            recs.append(analyze_entity(provider, account, campaign, adset, "Ad Set", "ABO", account_regime, regime_reason, account_3d_window, account_today, regime_inputs, config))
    if not recs:
        recs.append(data_error_recommendation(account, f"Cannot identify actual budget level. Account regime: {account_regime}. {regime_reason}"))
    return recs


def analyze_entity(
    provider: MetaDataProvider,
    account: Any,
    campaign: EntityInfo,
    adset: EntityInfo | None,
    entity_level: str,
    budget_model: str,
    account_regime: str,
    account_regime_reason: str,
    account_3d: rules.MetricWindow,
    account_today: InsightRecord,
    regime_inputs: dict[str, Any],
    config: dict[str, Any],
) -> BudgetRecommendation:
    entity = adset or campaign
    provider_level = "adset" if adset else "campaign"
    last_3d_record = provider.get_insights(account, provider_level, "last_3_complete_days", entity_id=entity.entity_id, entity_name=entity.entity_name)[0]
    today_record = provider.get_insights(account, provider_level, "today", entity_id=entity.entity_id, entity_name=entity.entity_name)[0]
    avg_30d_record = provider.get_insights(account, provider_level, "last_30_complete_days", entity_id=entity.entity_id, entity_name=entity.entity_name)[0]
    last_3d = metric_window(last_3d_record)
    today = metric_window(today_record)
    avg_30d = metric_window(avg_30d_record)
    rtg = rules.is_rtg(campaign.entity_name, config)
    confidence = "HIGH" if last_3d_record.data_status == "SUCCESS" and today_record.data_status == "SUCCESS" and rules.has_last_3d_sample(last_3d, config) and rules.has_today_sample(today, config) else "LOW"
    if last_3d_record.data_status == "ERROR" or today_record.data_status == "ERROR" or avg_30d_record.data_status == "ERROR":
        decision = rules.decision("DATA_ERROR", entity.daily_budget, config, "Meta Data Provider returned ERROR; budget changes are blocked.", False, "")
    elif last_3d_record.data_status != "SUCCESS" or today_record.data_status != "SUCCESS":
        decision = rules.decision("DATA_INSUFFICIENT", entity.daily_budget, config, "Meta Data Provider returned EMPTY data; budget changes are blocked.", False, "")
    else:
        decision = rules.evaluate_entity(entity_level, budget_model, rtg, account_regime, last_3d, today, avg_30d, entity.daily_budget, entity.learning_status, config)
    return BudgetRecommendation(
        account_name=account.name,
        account_id=account.account_id,
        account_regime=account_regime,
        account_3d_roas=fmt_optional(account_3d.roas),
        account_today_roas=fmt_optional(metric_window(account_today).roas),
        entity_level=entity_level,
        campaign_name=campaign.entity_name,
        campaign_id=campaign.entity_id,
        adset_name=adset.entity_name if adset else None,
        adset_id=adset.entity_id if adset else None,
        budget_model=budget_model,
        rtg="Yes" if rtg else "No",
        delivery_status=entity.effective_status,
        learning_status=entity.learning_status,
        current_budget=fmt_optional(entity.daily_budget),
        currency=entity.currency,
        last_3d_spend=fmt_decimal(last_3d.spend),
        last_3d_purchase=fmt_decimal(last_3d.purchase),
        last_3d_purchase_value=fmt_decimal(last_3d.purchase_value),
        last_3d_roas=fmt_optional(last_3d.roas),
        today_spend=fmt_decimal(today.spend),
        today_purchase=fmt_decimal(today.purchase),
        today_purchase_value=fmt_decimal(today.purchase_value),
        today_roas=fmt_optional(today.roas),
        atc_rate=fmt_optional_percent(today.atc_rate),
        checkout_rate=fmt_optional_percent(today.checkout_rate),
        funnel_anomaly=decision["funnel_anomaly"],
        data_confidence=confidence,
        proposed_action=decision["proposed_action"],
        proposed_new_budget=decision["proposed_new_budget"],
        adjustment_percentage=decision["adjustment_percentage"],
        reason=decision["reason"],
        optimization_hint=decision["optimization_hint"],
        account_regime_reason=account_regime_reason,
        matched_rule=f"{budget_model}_{'RTG' if rtg else 'NON_RTG'}_{entity_level}",
        cooldown_status="CLEAR",
        api_result=today_record.data_status,
        account_timezone=today_record.timezone,
        today_request_since=today_record.since,
        today_request_until=today_record.until,
        today_date_preset=today_record.date_preset or "",
        today_raw_has_data="Yes" if today_record.data_status == "SUCCESS" else "No",
        today_raw_spend=str(today_record.raw_spend or "N/A"),
        today_raw_actions=[{"action_type": item} for item in today_record.raw_action_types],
        today_raw_action_values=[{"action_type": item} for item in today_record.raw_action_value_types],
        today_raw_data=list(today_record.raw_rows_sample),
        parsed_today_purchase=fmt_decimal(today.purchase),
        parsed_today_atc=fmt_decimal(today.atc),
        parsed_today_checkout=fmt_decimal(today.checkout),
        parsed_today_link_clicks=fmt_decimal(today.clicks),
        regime_calculation_inputs=regime_inputs,
    )


def metric_window(record: InsightRecord) -> rules.MetricWindow:
    return rules.MetricWindow(
        spend=decimal_or_zero(record.spend),
        purchase=decimal_or_zero(record.purchase),
        purchase_value=decimal_or_zero(record.purchase_value),
        atc=decimal_or_zero(record.add_to_cart),
        checkout=decimal_or_zero(record.checkout),
        clicks=decimal_or_zero(record.link_clicks),
        impressions=decimal_or_zero(record.impressions),
    )


def account_regime_from_records(
    account_3d: InsightRecord,
    account_today: InsightRecord,
    account_3d_window: rules.MetricWindow,
    account_today_window: rules.MetricWindow,
    funnel_anomaly: bool,
    config: dict[str, Any],
) -> tuple[str, str]:
    if account_3d.data_status != "SUCCESS":
        return "DATA_INSUFFICIENT", f"Account 3D data_status is {account_3d.data_status}; account regime cannot be classified."
    if account_3d.spend is None or account_3d.purchase_value is None or account_3d.roas is None:
        return "DATA_INSUFFICIENT", "Account 3D spend, purchase value, or ROAS is unavailable; account regime cannot be classified."
    if account_today.data_status == "ERROR":
        return "DATA_INSUFFICIENT", "Account today data_status is ERROR; account regime cannot use today."
    return rules.determine_account_regime(account_3d_window, account_today_window, funnel_anomaly, config)


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
        learning_status="N/A",
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
        optimization_hint="Meta API request failed or required data is missing; budget changes are blocked.",
        account_regime_reason=error,
        matched_rule="DATA_ERROR",
        cooldown_status="N/A",
        api_result="FAILED",
    )


def regime_debug(account_3d: InsightRecord, account_today: InsightRecord, regime: str, reason: str) -> dict[str, Any]:
    return {
        "account_id": account_3d.account_id,
        "account_name": account_3d.account_name,
        "account_timezone": account_3d.timezone,
        "account_timezone_offset_hours_utc": account_3d.timezone_offset_hours_utc,
        "account_3d_data_status": account_3d.data_status,
        "account_3d_spend": fmt_record_decimal(account_3d.spend),
        "account_3d_purchase": fmt_record_decimal(account_3d.purchase),
        "account_3d_purchase_value": fmt_record_decimal(account_3d.purchase_value),
        "account_3d_roas": fmt_optional(account_3d.roas),
        "account_today_data_status": account_today.data_status,
        "account_today_spend": fmt_record_decimal(account_today.spend),
        "account_today_purchase": fmt_record_decimal(account_today.purchase),
        "account_today_purchase_value": fmt_record_decimal(account_today.purchase_value),
        "account_today_roas": fmt_optional(account_today.roas),
        "regime_result": regime,
        "regime_reason": reason,
    }


def print_regime_debug(account_id: str, inputs: dict[str, Any]) -> None:
    print(
        "Account regime inputs | "
        f"account_id={account_id} | "
        f"3D Spend={inputs['account_3d_spend']} | "
        f"3D Purchase={inputs['account_3d_purchase']} | "
        f"3D Purchase Value={inputs['account_3d_purchase_value']} | "
        f"3D ROAS={inputs['account_3d_roas']} | "
        f"Today Spend={inputs['account_today_spend']} | "
        f"Today Purchase={inputs['account_today_purchase']} | "
        f"Today Purchase Value={inputs['account_today_purchase_value']} | "
        f"Today ROAS={inputs['account_today_roas']} | "
        f"Regime Result={inputs['regime_result']} | "
        f"Regime Reason={inputs['regime_reason']}"
    )


def fmt_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_record_decimal(value: Decimal | None) -> str:
    return "N/A" if value is None else fmt_decimal(value)


def fmt_optional(value: Decimal | None) -> str | None:
    return None if value is None else fmt_decimal(value)


def fmt_optional_percent(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    return fmt_decimal(value * Decimal("100")) + "%"


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
        f"Account Timezone: {item.get('account_timezone')}",
        f"Today Request: date_preset={item.get('today_date_preset') or 'N/A'}, since={item.get('today_request_since')}, until={item.get('today_request_until')}",
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
        f"Cooldown Status: {item.get('cooldown_status')}",
        f"Data Confidence: {item['data_confidence']}",
        f"Matched Rule: {item.get('matched_rule')}",
        f"Proposed Action: {item['proposed_action']}",
        f"Proposed New Budget: {item['proposed_new_budget']}",
        f"Adjustment Percentage: {item['adjustment_percentage']}",
        f"Reason: {item['reason']}",
        f"API Result: {item.get('api_result')}",
        f"Optimization Hint: {item['optimization_hint']}",
    ]
