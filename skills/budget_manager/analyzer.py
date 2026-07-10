from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from config import ACCOUNT_CONFIGS, META_ACCESS_TOKEN
from feishu import FeishuWebhookClient
from meta_api import MetaAPIError, MetaMarketingAPI
from skills.budget_manager import audit
from skills.budget_manager import rules


logger = logging.getLogger(__name__)

ZERO_DECIMAL = Decimal("0")
INSIGHT_FIELDS = "spend,actions,action_values,impressions,inline_link_clicks,clicks"
ACTION_TYPES = {
    "purchase": ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase", "onsite_conversion.purchase"),
    "purchase_value": ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase", "onsite_conversion.purchase"),
    "add_to_cart": ("add_to_cart", "offsite_conversion.fb_pixel_add_to_cart", "omni_add_to_cart"),
    "checkout": ("initiate_checkout", "offsite_conversion.fb_pixel_initiate_checkout", "omni_initiated_checkout"),
    "link_click": ("link_click",),
}


@dataclass(frozen=True)
class AccountContext:
    currency: str
    timezone_name: str
    account_today: date


@dataclass(frozen=True)
class MetricsResult:
    metrics: rules.MetricWindow
    request: dict[str, Any]
    raw_summary: dict[str, Any]


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
    run_id = "budget_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    start_time = datetime.now().isoformat(timespec="seconds")
    recommendations: list[BudgetRecommendation] = []
    target_accounts = [account.account_id for account in ACCOUNT_CONFIGS if account.account_type == config["performance_account_type"]]
    audit.append_log(config, {**audit.run_base(run_id, "preview", start_time, config, target_accounts), "event": "START"})

    performance_accounts = [account for account in ACCOUNT_CONFIGS if account.account_type == config["performance_account_type"]]
    for index, account in enumerate(performance_accounts, start=1):
        print(f"Processing Account {index}/{len(performance_accounts)}...")
        recs = analyze_account(api, account, config, run_id)
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


def analyze_account(api: MetaMarketingAPI, account: Any, config: dict[str, Any], run_id: str | None = None) -> list[BudgetRecommendation]:
    try:
        context = get_account_context(api, account)
        ranges = rules.date_ranges(context.account_today)
        account_3d = get_metrics(api, account.api_id, "account", time_range=ranges["last_3_complete_days"], account_id=account.account_id, account_timezone=context.timezone_name)
        account_today = get_metrics(api, account.api_id, "account", date_preset="today", account_id=account.account_id, account_timezone=context.timezone_name, expected_range=ranges["today"])
        account_30d = get_metrics(api, account.api_id, "account", time_range=ranges["last_30_complete_days"], account_id=account.account_id, account_timezone=context.timezone_name)
        account_funnel, _ = rules.detect_funnel_anomaly(account_today.metrics, account_30d.metrics, config)
        account_regime, regime_reason = rules.determine_account_regime(account_3d.metrics, account_today.metrics, account_funnel, config)
        regime_inputs = regime_debug(account_3d.metrics, account_today.metrics, regime_reason)
        print_regime_debug(account.account_id, regime_inputs)
        if run_id:
            audit.append_log(
                config,
                {
                    "run_id": run_id,
                    "mode": "preview",
                    "event": "ACCOUNT_TODAY_INSIGHTS",
                    "account_id": account.account_id,
                    "account_timezone": context.timezone_name,
                    "today_request": account_today.request,
                    "raw_insights_has_data": account_today.raw_summary["has_data"],
                    "raw_today_spend": account_today.raw_summary["spend"],
                    "raw_today_actions": account_today.raw_summary["actions"],
                    "raw_today_action_values": account_today.raw_summary["action_values"],
                    "parsed_purchase": fmt_decimal(account_today.metrics.purchase),
                    "parsed_atc": fmt_decimal(account_today.metrics.atc),
                    "parsed_checkout": fmt_decimal(account_today.metrics.checkout),
                },
            )
            audit.append_log(
                config,
                {
                    "run_id": run_id,
                    "mode": "preview",
                    "event": "ACCOUNT_REGIME",
                    "account_id": account.account_id,
                    "account_timezone": context.timezone_name,
                    **regime_inputs,
                },
            )
        print("Scanning Campaigns...")
        campaigns = get_campaigns(api, account)
        print("Scanning Ad Sets...")
        adsets = get_adsets(api, account)
    except Exception as exc:
        clean_error = sanitize_error(exc)
        logger.error("Budget Manager account scan failed | account_id=%s | error=%s", account.account_id, clean_error)
        return [data_error_recommendation(account, clean_error)]

    recs: list[BudgetRecommendation] = []
    print("Evaluating rules...")
    for campaign in campaigns:
        campaign_budget = parse_budget(campaign.get("daily_budget"), context.currency)
        has_campaign_budget = campaign_budget is not None or campaign.get("lifetime_budget")
        if has_campaign_budget:
            recs.append(
                analyze_entity(
                    api,
                    account,
                    campaign,
                    None,
                    "Campaign",
                    "CBO",
                    context,
                    ranges,
                    account_regime,
                    regime_reason,
                    account_3d.metrics,
                    account_today,
                    regime_inputs,
                    config,
                )
            )
            continue
        for adset in [row for row in adsets if row.get("campaign_id") == campaign.get("id") and row.get("daily_budget")]:
            recs.append(
                analyze_entity(
                    api,
                    account,
                    campaign,
                    adset,
                    "Ad Set",
                    "ABO",
                    context,
                    ranges,
                    account_regime,
                    regime_reason,
                    account_3d.metrics,
                    account_today,
                    regime_inputs,
                    config,
                )
            )
    if not recs:
        recs.append(data_error_recommendation(account, f"Cannot identify actual budget level. Account regime: {account_regime}. {regime_reason}"))
    return recs


def analyze_entity(
    api: MetaMarketingAPI,
    account: Any,
    campaign: dict[str, Any],
    adset: dict[str, Any] | None,
    entity_level: str,
    budget_model: str,
    context: AccountContext,
    ranges: dict[str, dict[str, str]],
    account_regime: str,
    account_regime_reason: str,
    account_3d: rules.MetricWindow,
    account_today: MetricsResult,
    regime_inputs: dict[str, Any],
    config: dict[str, Any],
) -> BudgetRecommendation:
    entity_id = str(adset.get("id") if adset else campaign.get("id"))
    level = "adset" if adset else "campaign"
    current_budget = parse_budget((adset or campaign).get("daily_budget"), context.currency)
    learning_status = extract_learning_status(adset)
    delivery_status = str((adset or campaign).get("effective_status") or "UNKNOWN")
    last_3d = get_metrics(api, entity_id, level, time_range=ranges["last_3_complete_days"], account_id=account.account_id, account_timezone=context.timezone_name)
    today = get_metrics(api, entity_id, level, date_preset="today", account_id=account.account_id, account_timezone=context.timezone_name, expected_range=ranges["today"])
    avg_30d = get_metrics(api, entity_id, level, time_range=ranges["last_30_complete_days"], account_id=account.account_id, account_timezone=context.timezone_name)
    rtg = rules.is_rtg(str(campaign.get("name") or ""), config)
    confidence = "HIGH" if rules.has_last_3d_sample(last_3d.metrics, config) and rules.has_today_sample(today.metrics, config) else "LOW"
    decision = rules.evaluate_entity(entity_level, budget_model, rtg, account_regime, last_3d.metrics, today.metrics, avg_30d.metrics, current_budget, learning_status, config)
    return BudgetRecommendation(
        account_name=account.name,
        account_id=account.account_id,
        account_regime=account_regime,
        account_3d_roas=fmt_optional(account_3d.roas),
        account_today_roas=fmt_optional(account_today.metrics.roas),
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
        currency=context.currency,
        last_3d_spend=fmt_decimal(last_3d.metrics.spend),
        last_3d_purchase=fmt_decimal(last_3d.metrics.purchase),
        last_3d_purchase_value=fmt_decimal(last_3d.metrics.purchase_value),
        last_3d_roas=fmt_optional(last_3d.metrics.roas),
        today_spend=fmt_decimal(today.metrics.spend),
        today_purchase=fmt_decimal(today.metrics.purchase),
        today_purchase_value=fmt_decimal(today.metrics.purchase_value),
        today_roas=fmt_optional(today.metrics.roas),
        atc_rate=fmt_optional_percent(today.metrics.atc_rate),
        checkout_rate=fmt_optional_percent(today.metrics.checkout_rate),
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
        api_result="SUCCESS",
        account_timezone=context.timezone_name,
        today_request_since=str(today.request.get("since") or ""),
        today_request_until=str(today.request.get("until") or ""),
        today_date_preset=str(today.request.get("date_preset") or ""),
        today_raw_has_data="Yes" if today.raw_summary["has_data"] else "No",
        today_raw_spend=str(today.raw_summary["spend"]),
        today_raw_actions=today.raw_summary["actions"],
        today_raw_action_values=today.raw_summary["action_values"],
        today_raw_data=today.raw_summary["data"],
        parsed_today_purchase=fmt_decimal(today.metrics.purchase),
        parsed_today_atc=fmt_decimal(today.metrics.atc),
        parsed_today_checkout=fmt_decimal(today.metrics.checkout),
        parsed_today_link_clicks=fmt_decimal(today.metrics.clicks),
        regime_calculation_inputs=regime_inputs,
    )


def get_account_context(api: MetaMarketingAPI, account: Any) -> AccountContext:
    payload = api._request(
        "GET",
        f"{api.base_url}/{account.api_id}",
        params={"fields": "currency,timezone_name,timezone_offset_hours_utc", "access_token": api.access_token},
    )
    currency = payload.get("currency")
    if not currency:
        raise RuntimeError("Currency is unavailable.")
    timezone_name = str(payload.get("timezone_name") or "UTC")
    return AccountContext(currency=str(currency), timezone_name=timezone_name, account_today=account_today(timezone_name))


def account_today(timezone_name: str) -> date:
    try:
        return datetime.now(ZoneInfo(timezone_name)).date()
    except ZoneInfoNotFoundError:
        return datetime.utcnow().date()


def get_campaigns(api: MetaMarketingAPI, account: Any) -> list[dict[str, Any]]:
    payload = api._request(
        "GET",
        f"{api.base_url}/{account.api_id}/campaigns",
        params={"fields": "id,name,effective_status,daily_budget,lifetime_budget", "limit": 200, "access_token": api.access_token},
    )
    return [row for row in payload.get("data", []) if row.get("effective_status") == "ACTIVE"]


def get_adsets(api: MetaMarketingAPI, account: Any) -> list[dict[str, Any]]:
    payload = api._request(
        "GET",
        f"{api.base_url}/{account.api_id}/adsets",
        params={"fields": "id,name,campaign_id,effective_status,daily_budget,lifetime_budget,learning_stage_info", "limit": 500, "access_token": api.access_token},
    )
    return [row for row in payload.get("data", []) if row.get("effective_status") == "ACTIVE"]


def get_metrics(
    api: MetaMarketingAPI,
    object_id: str,
    level: str,
    *,
    account_id: str,
    account_timezone: str,
    time_range: dict[str, str] | None = None,
    date_preset: str | None = None,
    expected_range: dict[str, str] | None = None,
) -> MetricsResult:
    params: dict[str, Any] = {
        "fields": INSIGHT_FIELDS,
        "level": level,
        "access_token": api.access_token,
    }
    request_debug: dict[str, Any] = {
        "account_id": account_id,
        "object_id": object_id,
        "level": level,
        "account_timezone": account_timezone,
        "date_preset": date_preset or "",
        "since": (expected_range or time_range or {}).get("since", ""),
        "until": (expected_range or time_range or {}).get("until", ""),
    }
    if date_preset:
        params["date_preset"] = date_preset
    elif time_range:
        params["time_range"] = json.dumps(time_range)
    else:
        raise ValueError("Either time_range or date_preset is required.")

    try:
        payload = api._request("GET", f"{api.base_url}/{object_id}/insights", params=params)
    except MetaAPIError as exc:
        logger.error(
            "Budget Manager insights failed | account_id=%s | object_id=%s | status=%s | meta_code=%s | message=%s",
            account_id,
            object_id,
            exc.http_status_code or "unavailable",
            exc.meta_error_code or "unavailable",
            exc,
        )
        raise
    rows = list(payload.get("data", []))
    metrics = rows_to_metrics(rows)
    raw_summary = summarize_raw_rows(rows)
    logger.info(
        "Budget Manager insights debug | account_id=%s | object_id=%s | timezone=%s | date_preset=%s | since=%s | until=%s | has_data=%s | raw_spend=%s | parsed_purchase=%s | parsed_atc=%s | parsed_checkout=%s",
        account_id,
        object_id,
        account_timezone,
        request_debug["date_preset"],
        request_debug["since"],
        request_debug["until"],
        raw_summary["has_data"],
        raw_summary["spend"],
        metrics.purchase,
        metrics.atc,
        metrics.checkout,
    )
    print(
        f"Insights debug | account_id={account_id} | timezone={account_timezone} | "
        f"date_preset={request_debug['date_preset'] or 'N/A'} | since={request_debug['since']} | until={request_debug['until']} | "
        f"raw spend={raw_summary['spend']} | raw actions={raw_summary['actions']} | raw action_values={raw_summary['action_values']} | "
        f"parsed purchase={metrics.purchase} | parsed ATC={metrics.atc} | parsed checkout={metrics.checkout}"
    )
    return MetricsResult(metrics=metrics, request=request_debug, raw_summary=raw_summary)


def rows_to_metrics(rows: list[dict[str, Any]]) -> rules.MetricWindow:
    spend = ZERO_DECIMAL
    purchase = ZERO_DECIMAL
    purchase_value = ZERO_DECIMAL
    atc = ZERO_DECIMAL
    checkout = ZERO_DECIMAL
    link_clicks = ZERO_DECIMAL
    impressions = ZERO_DECIMAL
    for row in rows:
        spend += Decimal(str(row.get("spend") or "0"))
        impressions += Decimal(str(row.get("impressions") or "0"))
        row_link_clicks = action_value(row.get("actions", []), ACTION_TYPES["link_click"])
        if row_link_clicks == 0 and row.get("inline_link_clicks") not in (None, ""):
            row_link_clicks = Decimal(str(row.get("inline_link_clicks") or "0"))
        link_clicks += row_link_clicks
        purchase += action_value(row.get("actions", []), ACTION_TYPES["purchase"])
        purchase_value += action_value(row.get("action_values", []), ACTION_TYPES["purchase_value"])
        atc += action_value(row.get("actions", []), ACTION_TYPES["add_to_cart"])
        checkout += action_value(row.get("actions", []), ACTION_TYPES["checkout"])
    return rules.MetricWindow(spend, purchase, purchase_value, atc, checkout, link_clicks, impressions)


def summarize_raw_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "has_data": bool(rows),
        "spend": str(sum((Decimal(str(row.get("spend") or "0")) for row in rows), ZERO_DECIMAL)),
        "actions": compact_action_rows(rows, "actions"),
        "action_values": compact_action_rows(rows, "action_values"),
        "data": rows[:3],
    }


def compact_action_rows(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    compacted: list[dict[str, Any]] = []
    interesting = set(ACTION_TYPES["purchase"] + ACTION_TYPES["add_to_cart"] + ACTION_TYPES["checkout"] + ACTION_TYPES["link_click"])
    for row in rows:
        for action in row.get(field, []) or []:
            action_type = str(action.get("action_type") or "")
            if action_type in interesting:
                compacted.append({"action_type": action_type, "value": str(action.get("value") or "0")})
    return compacted


def action_value(actions: list[dict[str, Any]], action_types: tuple[str, ...]) -> Decimal:
    by_type: dict[str, Decimal] = {}
    for row in actions or []:
        action_type = str(row.get("action_type") or "")
        if action_type and action_type not in by_type:
            by_type[action_type] = Decimal(str(row.get("value") or "0"))
    for action_type in action_types:
        if action_type in by_type:
            return by_type[action_type]
    return ZERO_DECIMAL


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
    if not isinstance(info, dict):
        return "N/A"
    raw_status = str(info.get("status") or info.get("phase") or info.get("learning_stage") or "").strip()
    normalized = raw_status.replace("_", " ").upper()
    if normalized in {"LEARNING", "LEARNING LIMITED"}:
        return normalized.title()
    return "N/A"


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


def regime_debug(last_3d: rules.MetricWindow, today: rules.MetricWindow, reason: str) -> dict[str, Any]:
    return {
        "account_3d_spend": fmt_decimal(last_3d.spend),
        "account_3d_purchase": fmt_decimal(last_3d.purchase),
        "account_3d_purchase_value": fmt_decimal(last_3d.purchase_value),
        "account_3d_roas": fmt_optional(last_3d.roas),
        "account_today_spend": fmt_decimal(today.spend),
        "account_today_purchase": fmt_decimal(today.purchase),
        "account_today_purchase_value": fmt_decimal(today.purchase_value),
        "account_today_roas": fmt_optional(today.roas),
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
        f"Today ROAS={inputs['account_today_roas']} | "
        f"Regime reason={inputs['regime_reason']}"
    )


def fmt_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


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
