from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from config import ACCOUNT_CONFIGS, ReportAccount, validate_config
from dashboard.data_loader import dashboard_summary, load_preview
from feishu import FeishuWebhookClient
from meta_api import MetaMarketingAPI
from meta_data_provider import AccountMeta, InsightRecord, MetaDataProvider, PeriodSpec, decimal_or_zero, sum_records


ReportMode = Literal["morning", "daily-close", "early-pulse"]
BEIJING_TZ = ZoneInfo("Asia/Shanghai")
SCHEDULED_REPORT_LOG = Path("logs/scheduled_reports.log")
SCHEDULED_REPORT_STATE = Path(os.getenv("SCHEDULED_REPORT_STATE_FILE", "scheduled_report_state.json"))
MAX_SCHEDULE_DELAY = timedelta(minutes=30)


@dataclass(frozen=True)
class ReportPlan:
    mode: ReportMode
    title: str
    scheduled_slot: str
    beijing_time: datetime
    account_local_time: datetime
    current_period: PeriodSpec
    comparison_7d: PeriodSpec
    comparison_30d: PeriodSpec
    same_time_window: bool
    confidence_floor: str
    note: str


@dataclass(frozen=True)
class AccountReportRow:
    account: ReportAccount
    meta: AccountMeta | None
    current: InsightRecord
    avg_7d: InsightRecord | None
    avg_30d: InsightRecord | None
    status: str
    summary: str
    last_7_complete_days: InsightRecord | None = None


def build_report_plan(mode: ReportMode, account_timezone: str = "America/Phoenix", now: datetime | None = None) -> ReportPlan:
    beijing_time = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    local_time = beijing_time.astimezone(ZoneInfo(account_timezone))
    today = local_time.date()
    if mode == "morning":
        current = PeriodSpec("today_same_time", today.isoformat(), today.isoformat(), includes_today=True)
        comp7 = PeriodSpec("last_7_same_time_average", (today - timedelta(days=7)).isoformat(), (today - timedelta(days=1)).isoformat())
        comp30 = PeriodSpec("last_30_same_time_average", (today - timedelta(days=30)).isoformat(), (today - timedelta(days=1)).isoformat())
        return ReportPlan(mode, "Meta Morning Realtime", "09:00 Asia/Shanghai", beijing_time, local_time, current, comp7, comp30, True, "MEDIUM", "")
    if mode == "daily-close":
        yesterday = today - timedelta(days=1)
        current = PeriodSpec("yesterday_complete_day", yesterday.isoformat(), yesterday.isoformat())
        comp7 = PeriodSpec("previous_7_complete_day_average", (yesterday - timedelta(days=7)).isoformat(), (yesterday - timedelta(days=1)).isoformat())
        comp30 = PeriodSpec("previous_30_complete_day_average", (yesterday - timedelta(days=30)).isoformat(), (yesterday - timedelta(days=1)).isoformat())
        return ReportPlan(mode, "Meta Daily Close", "15:30 Asia/Shanghai", beijing_time, local_time, current, comp7, comp30, False, "HIGH", "")
    if mode == "early-pulse":
        current = PeriodSpec("early_pulse_same_time", today.isoformat(), today.isoformat(), includes_today=True)
        comp7 = PeriodSpec("last_7_same_time_average", (today - timedelta(days=7)).isoformat(), (today - timedelta(days=1)).isoformat())
        comp30 = PeriodSpec("last_30_same_time_average", (today - timedelta(days=30)).isoformat(), (today - timedelta(days=1)).isoformat())
        note = "当前仍处于广告日早期，仅用于监测启动情况，不建议依据当前 ROAS 做强调整。"
        return ReportPlan(mode, "Meta Early Pulse", "18:00 Asia/Shanghai", beijing_time, local_time, current, comp7, comp30, True, "LOW", note)
    raise ValueError(f"Unsupported report mode: {mode}")


def run_scheduled_report(mode: ReportMode, as_of: str | None = None) -> int:
    validate_config()
    provider = MetaDataProvider(MetaMarketingAPI())
    rows: list[AccountReportRow] = []
    actual_start = datetime.now(BEIJING_TZ)
    # A delayed scheduler must not change the reporting date/window.  Anchor
    # production runs to the slot they were meant to execute at.
    start = parse_as_of(as_of) if as_of else scheduled_time(mode, actual_start)
    if as_of is None:
        ensure_schedule_fresh(start, actual_start)
    run_key = f"{start.date().isoformat()}:{mode}"
    state = load_report_state()
    previous = state.get("runs", {}).get(run_key, {})
    if previous.get("status") in {"SENDING", "SENT"}:
        write_skip_log(mode, start, actual_start, run_key, f"already_{previous['status'].lower()}")
        print(f"Scheduled report skipped: {run_key} already {previous['status'].lower()}")
        return 0
    save_report_state(state)
    plan: ReportPlan | None = None
    for account in ACCOUNT_CONFIGS:
        try:
            meta = provider.get_account_meta(account)
            account_plan = build_report_plan(mode, meta.timezone_name, start)
            plan = plan or account_plan
            current = fetch_period(provider, account, meta, account_plan.current_period, account_plan)
            avg_7d = fetch_period(provider, account, meta, account_plan.comparison_7d, account_plan, average_days=7)
            avg_30d = fetch_period(provider, account, meta, account_plan.comparison_30d, account_plan, average_days=30)
            last_7_complete = fetch_last_7_complete_days(provider, account, meta, account_plan) if account_plan.same_time_window else avg_7d
            status, summary = judge_account(account, current, avg_7d, account_plan)
            rows.append(AccountReportRow(account, meta, current, avg_7d, avg_30d, status, summary, last_7_complete))
        except Exception as exc:
            fallback_plan = plan or build_report_plan(mode)
            error = error_insight(account, fallback_plan.current_period, str(exc))
            rows.append(AccountReportRow(account, None, error, None, None, "DATA_ERROR", "Meta API failed; this account is excluded from health judgment."))

    plan = plan or build_report_plan(mode)
    if all(row.current.data_status == "ERROR" for row in rows):
        message = "Meta Report Data Fetch Failed\n\n本次数据不可用于判断广告表现。"
    else:
        message = format_report(plan, rows)
    data_ready_at = datetime.now(BEIJING_TZ)
    state.setdefault("runs", {})[run_key] = {"status": "SENDING", "updated_at": data_ready_at.isoformat(timespec="seconds")}
    save_report_state(state)
    send_result = "SUCCESS"
    sent_at: datetime | None = None
    feishu_sent = False
    try:
        FeishuWebhookClient().send_text(message)
        feishu_sent = True
        sent_at = datetime.now(BEIJING_TZ)
        state["runs"][run_key] = {"status": "SENT", "sent_at": sent_at.isoformat(timespec="seconds")}
        save_report_state(state)
    except Exception as exc:
        send_result = type(exc).__name__
        # If Feishu already accepted the message, retain the previously saved
        # SENDING marker so a retry cannot duplicate the report.
        if not feishu_sent:
            state["runs"].pop(run_key, None)
            save_report_state(state)
        write_log(plan, rows, send_result, actual_start, data_ready_at, sent_at, run_key, error_reason=str(exc))
        raise
    write_log(plan, rows, send_result, actual_start, data_ready_at, sent_at, run_key)
    print(f"Scheduled report sent: {mode}")
    return 0


def scheduled_time(mode: ReportMode, observed_at: datetime) -> datetime:
    observed = observed_at.astimezone(BEIJING_TZ)
    hour, minute = {"morning": (9, 0), "daily-close": (15, 30), "early-pulse": (18, 0)}[mode]
    scheduled = observed.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # If a run is delayed past Beijing midnight, the latest occurrence of the
    # slot belongs to the previous calendar day, not to a future slot today.
    return scheduled if scheduled <= observed else scheduled - timedelta(days=1)


def load_report_state() -> dict[str, Any]:
    if not SCHEDULED_REPORT_STATE.exists():
        return {"runs": {}}
    try:
        payload = json.loads(SCHEDULED_REPORT_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Scheduled report state read failed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("runs"), dict):
        raise RuntimeError("Scheduled report state is invalid")
    return payload


def save_report_state(state: dict[str, Any]) -> None:
    SCHEDULED_REPORT_STATE.parent.mkdir(parents=True, exist_ok=True)
    temp = SCHEDULED_REPORT_STATE.with_suffix(SCHEDULED_REPORT_STATE.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(SCHEDULED_REPORT_STATE)


def ensure_schedule_fresh(planned_at: datetime, actual_start: datetime) -> None:
    if os.getenv("ALLOW_STALE_SCHEDULED_REPORT", "").lower() in {"1", "true", "yes", "on"}:
        return
    delay = actual_start.astimezone(BEIJING_TZ) - planned_at.astimezone(BEIJING_TZ)
    if delay > MAX_SCHEDULE_DELAY:
        raise RuntimeError(
            f"Stale scheduled report suppressed: planned={planned_at.isoformat()} "
            f"actual={actual_start.isoformat()} delay_seconds={int(delay.total_seconds())}"
        )


def fetch_period(
    provider: MetaDataProvider,
    account: ReportAccount,
    meta: AccountMeta,
    period: PeriodSpec,
    plan: ReportPlan,
    average_days: int | None = None,
) -> InsightRecord:
    hourly = plan.account_local_time.hour if plan.same_time_window else None
    records = provider.get_insights_for_period(account, "account", period, meta=meta, hourly_until_hour=hourly)
    combined = sum_records(records, "account", period.period) if len(records) > 1 else records[0]
    if average_days and combined.data_status == "SUCCESS":
        return average_record(combined, average_days, period.period)
    return combined


def fetch_last_7_complete_days(
    provider: MetaDataProvider,
    account: ReportAccount,
    meta: AccountMeta,
    plan: ReportPlan,
) -> InsightRecord:
    yesterday = plan.account_local_time.date() - timedelta(days=1)
    period = PeriodSpec(
        "last_7_complete_days",
        (yesterday - timedelta(days=6)).isoformat(),
        yesterday.isoformat(),
    )
    records = provider.get_insights_for_period(account, "account", period, meta=meta)
    combined = sum_records(records, "account", period.period) if len(records) > 1 else records[0]
    return average_record(combined, 7, period.period) if combined.data_status == "SUCCESS" else combined


def average_record(record: InsightRecord, days: int, period: str) -> InsightRecord:
    divisor = Decimal(days)
    spend = decimal_or_zero(record.spend) / divisor
    purchase = decimal_or_zero(record.purchase) / divisor
    purchase_value = None if record.purchase_value is None else record.purchase_value / divisor
    impressions = decimal_or_zero(record.impressions) / divisor
    clicks = decimal_or_zero(record.clicks) / divisor
    link_clicks = decimal_or_zero(record.link_clicks) / divisor
    reach = decimal_or_zero(record.reach) / divisor
    return InsightRecord(
        **{
            **record.__dict__,
            "period": period,
            "spend": spend,
            "purchase": purchase,
            "purchase_value": purchase_value,
            "roas": safe_div(purchase_value, spend),
            "impressions": impressions,
            "clicks": clicks,
            "link_clicks": link_clicks,
            "reach": reach,
            "ctr": safe_div(clicks, impressions),
            "frequency": safe_div(impressions, reach),
        }
    )


def safe_div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def judge_account(account: ReportAccount, current: InsightRecord, avg_7d: InsightRecord | None, plan: ReportPlan) -> tuple[str, str]:
    if current.data_status == "ERROR":
        return "DATA_ERROR", "数据获取失败。"
    if current.data_status != "SUCCESS":
        return "DATA_INSUFFICIENT", "该时间段暂无有效投放数据。"
    if account.account_type == "brand":
        if current.reach is None or current.reach == 0 or current.frequency is None:
            return "DATA_INSUFFICIENT", "Brand Reach / Frequency 样本不足。"
        ctr_ratio = ratio(current.ctr, avg_7d.ctr if avg_7d else None)
        freq_ratio = ratio(current.frequency, avg_7d.frequency if avg_7d else None)
        if ctr_ratio is not None and ctr_ratio < Decimal("0.8"):
            return "WEAK", "Brand CTR 低于同口径历史。"
        if freq_ratio is not None and freq_ratio > Decimal("1.3"):
            return "WEAK", "Brand Frequency 上升。"
        return "HEALTHY", "Brand 启动正常。"
    if current.roas is None:
        reason = performance_missing_reason(current, plan)
        if plan.mode == "daily-close":
            return "DATA_ERROR", reason
        return "DATA_INSUFFICIENT", reason
    if plan.mode == "early-pulse" and decimal_or_zero(current.spend) < Decimal("80") and decimal_or_zero(current.purchase) < Decimal("1"):
        return "DATA_INSUFFICIENT", plan.note
    roas_ratio = ratio(current.roas, avg_7d.roas if avg_7d else None)
    if roas_ratio is not None and roas_ratio >= Decimal("1.2"):
        return "BULL", "ROAS 高于同口径历史。"
    if roas_ratio is not None and roas_ratio >= Decimal("0.9"):
        return "HEALTHY", "ROAS 接近或高于同口径历史。"
    if roas_ratio is not None and roas_ratio >= Decimal("0.75"):
        return "WEAK", "ROAS 低于同口径历史。"
    return "BEAR", "ROAS 明显低于同口径历史。"


def ratio(value: Decimal | None, base: Decimal | None) -> Decimal | None:
    if value is None or base is None or base == 0:
        return None
    return value / base


def format_report(plan: ReportPlan, rows: list[AccountReportRow]) -> str:
    success = [row for row in rows if row.current.data_status == "SUCCESS"]
    confidence = data_confidence(plan, rows)
    total_spend = sum((decimal_or_zero(row.current.spend) for row in success), Decimal("0"))
    total_purchase = sum((decimal_or_zero(row.current.purchase) for row in success), Decimal("0"))
    perf = [row for row in success if row.account.account_type == "performance"]
    perf_spend = sum((decimal_or_zero(row.current.spend) for row in perf), Decimal("0"))
    perf_purchase = sum((decimal_or_zero(row.current.purchase) for row in perf), Decimal("0"))
    perf_revenue = sum_purchase_value(perf)
    perf_roas = safe_div(perf_revenue, perf_spend)
    # Brand is upper-funnel and has no account-level Purchase ROAS judgment,
    # but its spend belongs in the blended business ROI denominator.
    overall_roi = safe_div(perf_revenue, total_spend)
    impressions = sum((decimal_or_zero(row.current.impressions) for row in success), Decimal("0"))
    clicks = sum((decimal_or_zero(row.current.clicks) for row in success), Decimal("0"))
    overall_status = overall_report_status(rows, confidence, perf_roas)
    preview = load_preview()
    review = dashboard_summary(preview)
    dashboard_url = os.getenv("DASHBOARD_URL") or "Dashboard URL not configured"
    lines = [
        plan.title,
        "",
        f"Scheduled for: Beijing {plan.beijing_time.strftime('%Y-%m-%d %H:%M')}",
        f"Data window: account date {plan.current_period.since}"
        + (f" to {plan.current_period.until}" if plan.current_period.until != plan.current_period.since else "")
        + (f", through hour {plan.account_local_time.hour:02d}:59 {plan.account_local_time.tzname()}" if plan.same_time_window else ", complete day"),
        f"Overall Status: {overall_status}",
        f"Data Confidence: {confidence}",
        f"Total Spend ({len(success)} accounts): {money(total_spend)}",
        f"Overall ROI: {fmt_optional(overall_roi)}",
        f"Performance ROAS: {fmt_optional(perf_roas)}",
        f"Purchase: {fmt(total_purchase)}",
        f"CPA: {money(safe_div(perf_spend, perf_purchase))}",
        f"CTR: {pct(safe_div(clicks, impressions))}",
        "",
        "Accounts:",
    ]
    lines.extend(account_line(row) for row in rows)
    lines.extend(
        [
            "",
            f"Review RUN_ID: {preview.run_id or 'N/A'}",
            f"Review data generated at: {preview.created_at or 'N/A'}",
            f"Pending: {review['pending']} | High Risk: {review['high_risk']} | Data Error: {review['data_error']}",
            "",
            f"View Dashboard: {dashboard_url}",
        ]
    )
    return "\n".join(lines)


def account_line(row: AccountReportRow) -> str:
    cur = row.current
    if row.account.account_type == "brand":
        return f"- {row.account.name}: {row.status} | Spend {money(cur.spend)} | CTR {pct(cur.ctr)} | CPM {money(cpm(cur))} | {row.summary}"
    fields = (
        f"- {row.account.name}: {row.status} | Spend {money(cur.spend)} | "
        f"Purchase {fmt_optional(cur.purchase)} | Purchase Value {money(cur.purchase_value)} | "
        f"ROAS {fmt_optional(cur.roas)} | Data Date {cur.since}"
        + (f" to {cur.until}" if cur.until != cur.since else "")
        + f" | Account Timezone {cur.timezone} | Data Status {cur.data_status}"
    )
    if cur.roas is None:
        fields += f" | Missing Reason: {row.summary}"
        if row.last_7_complete_days and row.last_7_complete_days.roas is not None:
            fields += f" | Last 7 Complete Days ROAS: {fmt_optional(row.last_7_complete_days.roas)}"
    else:
        fields += f" | {row.summary}"
    return fields


def performance_missing_reason(record: InsightRecord, plan: ReportPlan) -> str:
    if record.data_status == "ERROR":
        return f"Meta接口失败: {record.error or 'unknown error'}"
    if record.data_status == "EMPTY":
        return "当日数据尚未回传" if plan.same_time_window else "Meta返回空数据"
    if record.spend is None:
        return "Spend字段缺失，可能为账户或字段映射错误"
    if record.spend == 0:
        return "Spend为0，无法计算ROAS"
    if record.purchase is None:
        return "Purchase字段缺失，可能为账户或字段映射错误"
    if record.purchase_value is None:
        return "当日数据尚未完全回传：Purchase Value字段缺失" if plan.same_time_window else "Purchase Value字段缺失"
    return "ROAS字段映射或计算失败"


def cpm(record: InsightRecord) -> Decimal | None:
    if record.spend is None or record.impressions is None or record.impressions == 0:
        return None
    return record.spend / record.impressions * Decimal("1000")


def overall_health(rows: list[AccountReportRow]) -> str:
    statuses = {row.status for row in rows}
    if "DATA_ERROR" in statuses:
        return "PARTIAL"
    if "DATA_INSUFFICIENT" in statuses:
        return "DATA_INSUFFICIENT"
    if "SEVERE_BEAR" in statuses or "BEAR" in statuses:
        return "BEAR"
    if "WEAK" in statuses:
        return "WEAK"
    if "BULL" in statuses:
        return "BULL"
    if "HEALTHY" in statuses:
        return "HEALTHY"
    return "NEUTRAL"


def overall_report_status(rows: list[AccountReportRow], confidence: str, performance_roas: Decimal | None) -> str:
    if confidence == "LOW" and performance_roas is None:
        return "DATA_INSUFFICIENT"
    return overall_health(rows)


def data_confidence(plan: ReportPlan, rows: list[AccountReportRow]) -> str:
    if any(row.current.data_status == "ERROR" for row in rows):
        return "LOW"
    if plan.confidence_floor == "LOW":
        return "LOW"
    if any(row.status == "DATA_INSUFFICIENT" for row in rows):
        return "LOW"
    return plan.confidence_floor


def sum_purchase_value(rows: list[AccountReportRow]) -> Decimal | None:
    if any(decimal_or_zero(row.current.purchase) > 0 and row.current.purchase_value is None for row in rows):
        return None
    values = [row.current.purchase_value for row in rows if row.current.purchase_value is not None]
    if not values and any(decimal_or_zero(row.current.purchase) > 0 for row in rows):
        return None
    return sum((decimal_or_zero(value) for value in values), Decimal("0"))


def fmt(value: Decimal | None) -> str:
    return "N/A" if value is None else str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_optional(value: Decimal | None) -> str:
    return fmt(value)


def money(value: Decimal | None) -> str:
    return "N/A" if value is None else "$" + fmt(value)


def pct(value: Decimal | None) -> str:
    return "N/A" if value is None else fmt(value * Decimal("100")) + "%"


def parse_as_of(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=BEIJING_TZ)
    return parsed.astimezone(BEIJING_TZ)


def error_insight(account: ReportAccount, period: PeriodSpec, error: str) -> InsightRecord:
    return InsightRecord(
        account_id=account.account_id,
        account_name=account.name,
        timezone="unknown",
        timezone_offset_hours_utc=None,
        currency="USD",
        level="account",
        entity_id=account.account_id,
        entity_name=account.name,
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
        error=error,
    )


def write_log(
    plan: ReportPlan,
    rows: list[AccountReportRow],
    feishu_result: str,
    actual_start: datetime | None = None,
    data_ready_at: datetime | None = None,
    sent_at: datetime | None = None,
    run_key: str | None = None,
    error_reason: str | None = None,
) -> None:
    started_at = actual_start or datetime.now(BEIJING_TZ)
    payload: dict[str, Any] = {
        "message_type": "scheduled_report",
        "created_at": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
        "report_mode": plan.mode,
        "scheduled_slot": plan.scheduled_slot,
        "planned_beijing_time": plan.beijing_time.isoformat(timespec="seconds"),
        "beijing_time": plan.beijing_time.isoformat(timespec="seconds"),
        "actual_start": started_at.isoformat(timespec="seconds"),
        "triggered_at": os.getenv("TRIGGERED_AT") or None,
        "started_at": started_at.isoformat(timespec="seconds"),
        "data_ready_at": data_ready_at.isoformat(timespec="seconds") if data_ready_at else None,
        "sent_at": sent_at.isoformat(timespec="seconds") if sent_at else None,
        "delay_minutes": round(((sent_at or datetime.now(BEIJING_TZ)) - plan.beijing_time).total_seconds() / 60, 2),
        "run_key": run_key or f"{plan.beijing_time.date().isoformat()}:{plan.mode}",
        "send_status": feishu_result,
        "skip_reason": None,
        "error_reason": error_reason,
        "scheduler_delay_seconds": int((started_at - plan.beijing_time).total_seconds()),
        "account_local_time": plan.account_local_time.isoformat(timespec="seconds"),
        "account_timezone": plan.account_local_time.tzname(),
        "query_date": plan.current_period.since,
        "cutoff_hour": plan.account_local_time.hour if plan.same_time_window else None,
        "data_range": {"since": plan.current_period.since, "until": plan.current_period.until, "date_preset": plan.current_period.date_preset},
        "comparison_range": {"7d": [plan.comparison_7d.since, plan.comparison_7d.until], "30d": [plan.comparison_30d.since, plan.comparison_30d.until]},
        "accounts_success": sum(1 for row in rows if row.current.data_status == "SUCCESS"),
        "accounts_failed": sum(1 for row in rows if row.current.data_status == "ERROR"),
        "accounts": [
            {
                "account_name": row.account.name,
                "account_id": row.account.account_id,
                "timezone": row.current.timezone,
                "currency": row.current.currency,
                "query_since": row.current.since,
                "query_until": row.current.until,
                "raw_spend": row.current.raw_spend,
                "spend": str(row.current.spend) if row.current.spend is not None else None,
                "purchase": str(row.current.purchase) if row.current.purchase is not None else None,
                "purchase_value": str(row.current.purchase_value) if row.current.purchase_value is not None else None,
                "roas": str(row.current.roas) if row.current.roas is not None else None,
                "data_status": row.current.data_status,
                "error": row.current.error,
                "report_status": row.status,
                "missing_reason": row.summary if row.account.account_type == "performance" and row.current.roas is None else None,
            }
            for row in rows
        ],
        "feishu_send_result": feishu_result,
        "dashboard_url_status": "configured" if os.getenv("DASHBOARD_URL") else "missing",
        "overall_status": overall_health(rows) if rows else "DATA_ERROR",
    }
    SCHEDULED_REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SCHEDULED_REPORT_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_skip_log(mode: ReportMode, planned_at: datetime, started_at: datetime, run_key: str, reason: str) -> None:
    SCHEDULED_REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "message_type": "scheduled_report",
        "report_mode": mode,
        "planned_at": planned_at.isoformat(timespec="seconds"),
        "triggered_at": os.getenv("TRIGGERED_AT") or None,
        "started_at": started_at.isoformat(timespec="seconds"),
        "data_ready_at": None,
        "sent_at": None,
        "delay_minutes": round((started_at - planned_at).total_seconds() / 60, 2),
        "run_key": run_key,
        "send_status": "SKIPPED",
        "skip_reason": reason,
        "error_reason": None,
        "created_at": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
    }
    with SCHEDULED_REPORT_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
