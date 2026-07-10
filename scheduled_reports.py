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


def build_report_plan(mode: ReportMode, account_timezone: str = "America/Phoenix", now: datetime | None = None) -> ReportPlan:
    beijing_time = (now or datetime.now(BEIJING_TZ)).astimezone(BEIJING_TZ)
    local_time = beijing_time.astimezone(ZoneInfo(account_timezone))
    today = local_time.date()
    if mode == "morning":
        current = PeriodSpec("today_same_time", today.isoformat(), today.isoformat(), "today", True)
        comp7 = PeriodSpec("last_7_same_time_average", (today - timedelta(days=7)).isoformat(), (today - timedelta(days=1)).isoformat())
        comp30 = PeriodSpec("last_30_same_time_average", (today - timedelta(days=30)).isoformat(), (today - timedelta(days=1)).isoformat())
        return ReportPlan(mode, "🌅 Meta Morning Realtime", "09:00 Asia/Shanghai", beijing_time, local_time, current, comp7, comp30, True, "MEDIUM", "")
    if mode == "daily-close":
        yesterday = today - timedelta(days=1)
        current = PeriodSpec("yesterday_complete_day", yesterday.isoformat(), yesterday.isoformat())
        comp7 = PeriodSpec("previous_7_complete_day_average", (yesterday - timedelta(days=7)).isoformat(), (yesterday - timedelta(days=1)).isoformat())
        comp30 = PeriodSpec("previous_30_complete_day_average", (yesterday - timedelta(days=30)).isoformat(), (yesterday - timedelta(days=1)).isoformat())
        return ReportPlan(mode, "📊 Meta Daily Close", "15:30 Asia/Shanghai", beijing_time, local_time, current, comp7, comp30, False, "HIGH", "")
    if mode == "early-pulse":
        current = PeriodSpec("early_pulse_same_time", today.isoformat(), today.isoformat(), "today", True)
        comp7 = PeriodSpec("last_7_same_time_average", (today - timedelta(days=7)).isoformat(), (today - timedelta(days=1)).isoformat())
        comp30 = PeriodSpec("last_30_same_time_average", (today - timedelta(days=30)).isoformat(), (today - timedelta(days=1)).isoformat())
        note = "当前仍处于广告日早期，仅用于监测启动情况，不建议依据当前 ROAS 做强调整。"
        return ReportPlan(mode, "🌙 Meta Early Pulse", "18:00 Asia/Shanghai", beijing_time, local_time, current, comp7, comp30, True, "LOW", note)
    raise ValueError(f"Unsupported report mode: {mode}")


def run_scheduled_report(mode: ReportMode) -> int:
    validate_config()
    provider = MetaDataProvider(MetaMarketingAPI())
    rows: list[AccountReportRow] = []
    start = datetime.now(BEIJING_TZ)
    plan: ReportPlan | None = None
    for account in ACCOUNT_CONFIGS:
        try:
            meta = provider.get_account_meta(account)
            account_plan = build_report_plan(mode, meta.timezone_name, start)
            plan = plan or account_plan
            current = fetch_period(provider, account, meta, account_plan.current_period, account_plan)
            avg_7d = fetch_period(provider, account, meta, account_plan.comparison_7d, account_plan, average_days=7)
            avg_30d = fetch_period(provider, account, meta, account_plan.comparison_30d, account_plan, average_days=30)
            status, summary = judge_account(account, current, avg_7d, account_plan)
            rows.append(AccountReportRow(account, meta, current, avg_7d, avg_30d, status, summary))
        except Exception as exc:
            fallback_plan = plan or build_report_plan(mode)
            error = error_insight(account, fallback_plan.current_period, str(exc))
            rows.append(AccountReportRow(account, None, error, None, None, "DATA_ERROR", "Meta API failed; this account is excluded from health judgment."))

    plan = plan or build_report_plan(mode)
    message = format_report(plan, rows)
    if all(row.current.data_status == "ERROR" for row in rows):
        message = "⚠ Meta Report Data Fetch Failed\n\n本次数据不可用于判断广告表现。"
    send_result = "SUCCESS"
    try:
        FeishuWebhookClient().send_text(message)
    except Exception as exc:
        send_result = type(exc).__name__
        write_log(plan, rows, send_result)
        raise
    write_log(plan, rows, send_result)
    print(f"Scheduled report sent: {mode}")
    return 0


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
        ctr = ratio(current.ctr, avg_7d.ctr if avg_7d else None)
        freq = ratio(current.frequency, avg_7d.frequency if avg_7d else None)
        if ctr is not None and ctr < Decimal("0.8"):
            return "WEAK", "Brand CTR 低于同口径历史，需要观察素材吸引力。"
        if freq is not None and freq > Decimal("1.3"):
            return "WEAK", "Brand Frequency 上升，需要观察触达疲劳。"
        return "HEALTHY", "Brand 指标无明显异常。"
    if plan.mode == "early-pulse" and decimal_or_zero(current.spend) < Decimal("80") and decimal_or_zero(current.purchase) < Decimal("1"):
        return "DATA_INSUFFICIENT", plan.note
    if current.roas is None:
        return "DATA_INSUFFICIENT", "Purchase / ROAS 样本不足，暂不做强判断。"
    base_roas = avg_7d.roas if avg_7d else None
    roas_ratio = ratio(current.roas, base_roas)
    if roas_ratio is not None and roas_ratio >= Decimal("1.2"):
        return "BULL", "ROAS 明显高于同口径历史。"
    if roas_ratio is not None and roas_ratio >= Decimal("0.9"):
        return "HEALTHY", "ROAS 接近或高于同口径历史。"
    if roas_ratio is not None and roas_ratio >= Decimal("0.75"):
        return "WEAK", "ROAS 低于同口径历史，需要观察。"
    return "BEAR", "ROAS 明显低于同口径历史。"


def ratio(value: Decimal | None, base: Decimal | None) -> Decimal | None:
    if value is None or base is None or base == 0:
        return None
    return value / base


def format_report(plan: ReportPlan, rows: list[AccountReportRow]) -> str:
    success = [row for row in rows if row.current.data_status == "SUCCESS"]
    overall_status = "PARTIAL" if len(success) != len(rows) else overall_health(rows)
    total_spend = sum((decimal_or_zero(row.current.spend) for row in success), Decimal("0"))
    total_purchase = sum((decimal_or_zero(row.current.purchase) for row in success), Decimal("0"))
    total_revenue = sum((decimal_or_zero(row.current.purchase_value) for row in success), Decimal("0"))
    perf = [row for row in success if row.account.account_type == "performance"]
    perf_spend = sum((decimal_or_zero(row.current.spend) for row in perf), Decimal("0"))
    perf_purchase = sum((decimal_or_zero(row.current.purchase) for row in perf), Decimal("0"))
    perf_revenue = sum((decimal_or_zero(row.current.purchase_value) for row in perf), Decimal("0"))
    impressions = sum((decimal_or_zero(row.current.impressions) for row in success), Decimal("0"))
    clicks = sum((decimal_or_zero(row.current.clicks) for row in success), Decimal("0"))
    reach = sum((decimal_or_zero(row.current.reach) for row in success), Decimal("0"))
    review = dashboard_summary(load_preview())
    dashboard_url = os.getenv("DASHBOARD_URL") or "Dashboard URL not configured"
    lines = [
        plan.title,
        "",
        f"北京时间：{plan.beijing_time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"账户当地时间：{plan.account_local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"数据范围：{plan.current_period.since} to {plan.current_period.until} ({'same-time window' if plan.same_time_window else 'complete day'})",
        "",
        "【1. Overall Summary】",
        f"- Overall Status: {overall_status}",
        f"- Total Spend: {money(total_spend)}",
        f"- Total Purchase: {fmt(total_purchase)}",
        f"- Total Revenue: {money(total_revenue)}",
        f"- All-account Blended ROAS: {fmt_optional(safe_div(total_revenue, total_spend))}",
        f"- Performance-account ROAS: {fmt_optional(safe_div(perf_revenue, perf_spend))}",
        f"- Performance-account CPA: {money(safe_div(perf_spend, perf_purchase))}",
        f"- Weighted CTR: {pct(safe_div(clicks, impressions))}",
        f"- Weighted Frequency: {fmt_optional(safe_div(impressions, reach))}",
        f"- Data Confidence: {data_confidence(plan, rows)}",
        "",
        "【2. Account Status】",
    ]
    for row in rows:
        lines.append(account_line(row))
    lines.extend(
        [
            "",
            "【3. Review Summary】",
            f"- Suggestions: {review['total']}",
            f"- Pending Approval: {review['pending']}",
            f"- Approved: {review['approved']}",
            f"- Rejected: {review['rejected']}",
            f"- High Risk: {review['high_risk']}",
            f"- Data Error: {review['data_error']}",
            "",
            "【4. Health Summary】",
            *health_summary(plan, rows, overall_status),
            "",
            "【5. Dashboard】",
            "View More:",
            dashboard_url,
        ]
    )
    return "\n".join(lines)


def account_line(row: AccountReportRow) -> str:
    cur = row.current
    if row.account.account_type == "brand":
        return f"- {row.account.name}: {row.status} | Spend {money(cur.spend)} | CTR {pct(cur.ctr)} | CPM {money(cpm(cur))} | Frequency {fmt_optional(cur.frequency)} | Reach {fmt_optional(cur.reach)} | {row.summary}"
    return f"- {row.account.name}: {row.status} | Spend {money(cur.spend)} | Purchase {fmt_optional(cur.purchase)} | ROAS {fmt_optional(cur.roas)} | CPA {money(safe_div(cur.spend, cur.purchase))} | CTR {pct(cur.ctr)} | Frequency {fmt_optional(cur.frequency)} | {row.summary}"


def cpm(record: InsightRecord) -> Decimal | None:
    if record.spend is None or record.impressions is None or record.impressions == 0:
        return None
    return record.spend / record.impressions * Decimal("1000")


def overall_health(rows: list[AccountReportRow]) -> str:
    statuses = {row.status for row in rows}
    if "SEVERE_BEAR" in statuses or "BEAR" in statuses:
        return "BEAR"
    if "WEAK" in statuses:
        return "WEAK"
    if "BULL" in statuses:
        return "BULL"
    if "HEALTHY" in statuses:
        return "HEALTHY"
    return "NEUTRAL"


def data_confidence(plan: ReportPlan, rows: list[AccountReportRow]) -> str:
    if any(row.current.data_status == "ERROR" for row in rows):
        return "LOW"
    if plan.confidence_floor == "LOW":
        return "LOW"
    if any(row.status == "DATA_INSUFFICIENT" for row in rows):
        return "LOW"
    return plan.confidence_floor


def health_summary(plan: ReportPlan, rows: list[AccountReportRow], overall_status: str) -> list[str]:
    lines = [f"- 整体状态：{overall_status}。"]
    weak = next((row for row in rows if row.status in {"BEAR", "WEAK", "DATA_ERROR"}), None)
    lines.append(f"- 重点账户：{weak.account.name}，{weak.summary}" if weak else "- 重点账户：暂无明显异常。")
    if plan.note:
        lines.append(f"- 当前策略：{plan.note}")
    elif overall_status in {"BEAR", "SEVERE_BEAR"}:
        lines.append("- 当前策略：优先保护预算，避免激进扩量。")
    else:
        lines.append("- 当前策略：继续观察 Dashboard 审批队列。")
    return lines[:3]


def fmt(value: Decimal | None) -> str:
    return "N/A" if value is None else str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_optional(value: Decimal | None) -> str:
    return fmt(value)


def money(value: Decimal | None) -> str:
    return "N/A" if value is None else "$" + fmt(value)


def pct(value: Decimal | None) -> str:
    return "N/A" if value is None else fmt(value * Decimal("100")) + "%"


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


def write_log(plan: ReportPlan, rows: list[AccountReportRow], feishu_result: str) -> None:
    payload: dict[str, Any] = {
        "created_at": datetime.now(BEIJING_TZ).isoformat(timespec="seconds"),
        "report_mode": plan.mode,
        "scheduled_slot": plan.scheduled_slot,
        "beijing_time": plan.beijing_time.isoformat(timespec="seconds"),
        "account_local_time": plan.account_local_time.isoformat(timespec="seconds"),
        "data_range": {"since": plan.current_period.since, "until": plan.current_period.until, "date_preset": plan.current_period.date_preset},
        "comparison_range": {"7d": [plan.comparison_7d.since, plan.comparison_7d.until], "30d": [plan.comparison_30d.since, plan.comparison_30d.until]},
        "accounts_success": sum(1 for row in rows if row.current.data_status == "SUCCESS"),
        "accounts_failed": sum(1 for row in rows if row.current.data_status == "ERROR"),
        "feishu_send_result": feishu_result,
        "dashboard_url_status": "configured" if os.getenv("DASHBOARD_URL") else "missing",
        "overall_status": overall_health(rows) if rows else "DATA_ERROR",
    }
    SCHEDULED_REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with SCHEDULED_REPORT_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")
