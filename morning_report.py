from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from config import ReportAccount
from meta_api import MetaAPIError, MetaMarketingAPI
from notifier import money


logger = logging.getLogger(__name__)

PURCHASE_ACTION_TYPES = (
    "purchase",
    "omni_purchase",
    "offsite_conversion.fb_pixel_purchase",
    "onsite_conversion.purchase",
)


@dataclass(frozen=True)
class Metrics:
    spend: Decimal = Decimal("0")
    purchase: Decimal = Decimal("0")
    revenue: Decimal = Decimal("0")
    clicks: Decimal = Decimal("0")
    impressions: Decimal = Decimal("0")
    reach: Decimal = Decimal("0")

    @property
    def roas(self) -> Decimal:
        return safe_div(self.revenue, self.spend)

    @property
    def cpa(self) -> Decimal:
        return safe_div(self.spend, self.purchase)

    @property
    def ctr(self) -> Decimal:
        return safe_div(self.clicks, self.impressions)

    @property
    def frequency(self) -> Decimal:
        return safe_div(self.impressions, self.reach)

    def daily_average(self, days: int) -> Metrics:
        divisor = Decimal(days)
        return Metrics(
            spend=self.spend / divisor,
            purchase=self.purchase / divisor,
            revenue=self.revenue / divisor,
            clicks=self.clicks / divisor,
            impressions=self.impressions / divisor,
            reach=self.reach / divisor,
        )


@dataclass(frozen=True)
class AccountReport:
    account: ReportAccount
    currency: str
    correct_balance: Decimal | None
    today: Metrics
    last_7d_avg: Metrics
    campaigns: list[tuple[str, Metrics]]

    @property
    def estimated_days_remaining(self) -> Decimal | None:
        if self.correct_balance is None or self.last_7d_avg.spend == 0:
            return None
        return self.correct_balance / self.last_7d_avg.spend


@dataclass(frozen=True)
class AccountReportFailure:
    account: ReportAccount
    error_message: str


def safe_div(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def required_decimal(row: dict[str, Any], field: str) -> Decimal:
    if field not in row:
        raise ValueError(f"Insights row missing required field: {field}")
    return as_decimal(row.get(field))


def extract_action_value(actions: list[dict[str, Any]]) -> Decimal:
    by_type = {str(row.get("action_type")): as_decimal(row.get("value")) for row in actions}
    for action_type in PURCHASE_ACTION_TYPES:
        if action_type in by_type:
            return by_type[action_type]
    return Decimal("0")


def metric_from_rows(rows: list[dict[str, Any]]) -> Metrics:
    total = Metrics()
    for row in rows:
        total = Metrics(
            spend=total.spend + required_decimal(row, "spend"),
            purchase=total.purchase + extract_action_value(row.get("actions", [])),
            revenue=total.revenue + extract_action_value(row.get("action_values", [])),
            clicks=total.clicks + required_decimal(row, "clicks"),
            impressions=total.impressions + required_decimal(row, "impressions"),
            reach=total.reach + required_decimal(row, "reach"),
        )
    return total


def campaign_metrics_from_rows(rows: list[dict[str, Any]]) -> list[tuple[str, Metrics]]:
    campaigns: list[tuple[str, Metrics]] = []
    for row in rows:
        name = str(row.get("campaign_name") or row.get("campaign_id") or "Unknown Campaign")
        campaigns.append((name, metric_from_rows([row])))
    return campaigns


def combine_metrics(metrics: list[Metrics]) -> Metrics:
    return Metrics(
        spend=sum((metric.spend for metric in metrics), Decimal("0")),
        purchase=sum((metric.purchase for metric in metrics), Decimal("0")),
        revenue=sum((metric.revenue for metric in metrics), Decimal("0")),
        clicks=sum((metric.clicks for metric in metrics), Decimal("0")),
        impressions=sum((metric.impressions for metric in metrics), Decimal("0")),
        reach=sum((metric.reach for metric in metrics), Decimal("0")),
    )


def fmt_number(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_ratio(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))


def fmt_plain_percent(value: Decimal) -> str:
    percent = value * Decimal("100")
    return f"{percent.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}%"


def fmt_optional_money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return "Balance source unavailable"
    return money(value, currency)


def fmt_optional_days(value: Decimal | None) -> str:
    if value is None:
        return "Balance source unavailable"
    return fmt_number(value)


def display_account_type(account: ReportAccount) -> str:
    if account.account_type == "brand":
        return "Brand Account"
    return "Performance Account"


def sanitize_error(exc: Exception) -> str:
    if isinstance(exc, MetaAPIError):
        status = exc.http_status_code or "unavailable"
        code = exc.meta_error_code or "unavailable"
        return f"HTTP Status Code: {status}; Meta Error Code: {code}; Error Message: {exc}"
    return type(exc).__name__


def log_raw_insights(account: ReportAccount, date_preset: str, rows: list[dict[str, Any]]) -> None:
    raw = metric_from_rows(rows) if rows else Metrics()
    logger.info(
        "Morning Report Meta raw insights | account_id=%s | date_preset=%s | raw spend=%s | raw impressions=%s | raw clicks=%s | raw purchase=%s | raw purchase value=%s",
        account.account_id,
        date_preset,
        raw.spend,
        raw.impressions,
        raw.clicks,
        raw.purchase,
        raw.revenue,
    )
    if date_preset == "today" and raw.spend == 0:
        logger.warning(
            "Morning Report today raw spend is 0 for account_id=%s. Check Meta account timezone, permissions, and whether delivery has started today.",
            account.account_id,
        )


def fetch_account_report(api: MetaMarketingAPI, account: ReportAccount) -> AccountReport:
    correct_balance, currency = api.get_spend_limit_balance(account)
    today_rows = api.get_account_insights(account, "today")
    log_raw_insights(account, "today", today_rows)
    today = metric_from_rows(today_rows)

    last_7d_rows = api.get_account_insights(account, "last_7d")
    log_raw_insights(account, "last_7d", last_7d_rows)
    last_7d_avg = metric_from_rows(last_7d_rows).daily_average(7)

    campaign_rows = api.get_campaign_insights(account, "today")
    log_raw_insights(account, "today campaign", campaign_rows)
    campaigns = campaign_metrics_from_rows(campaign_rows)
    return AccountReport(
        account=account,
        currency=currency,
        correct_balance=correct_balance,
        today=today,
        last_7d_avg=last_7d_avg,
        campaigns=campaigns,
    )


def build_morning_report(accounts: list[ReportAccount], api: MetaMarketingAPI) -> str:
    if len(accounts) != 3:
        raise ValueError("Morning Report V1 requires exactly 3 report accounts.")

    logger.info("Morning Report total configured accounts: %s", len(accounts))
    results: list[AccountReport | AccountReportFailure] = []
    for index, account in enumerate(accounts, start=1):
        logger.info("Processing account %s/%s: %s / %s", index, len(accounts), account.name, account.account_id)
        try:
            results.append(fetch_account_report(api, account))
        except Exception as exc:
            results.append(AccountReportFailure(account=account, error_message=sanitize_error(exc)))

    reports = [result for result in results if isinstance(result, AccountReport)]
    currency = reports[0].currency if reports else "USD"
    overall_today = combine_metrics([report.today for report in reports])
    total_balance = sum_correct_balances(reports)
    total_7d_spend = sum((report.last_7d_avg.spend for report in reports), Decimal("0"))
    estimated_days = None if total_balance is None or total_7d_spend == 0 else total_balance / total_7d_spend

    lines: list[str] = ["Morning Report V1", ""]
    lines.extend(overall_section(overall_today, total_balance, estimated_days, currency))
    lines.extend(account_section(results))
    lines.extend(campaign_section(results))
    return "\n".join(lines)


def sum_correct_balances(reports: list[AccountReport]) -> Decimal | None:
    if not reports or any(report.correct_balance is None for report in reports):
        return None
    return sum((report.correct_balance for report in reports), Decimal("0"))


def overall_section(
    today: Metrics,
    total_balance: Decimal | None,
    estimated_days: Decimal | None,
    currency: str,
) -> list[str]:
    return [
        "A. Overall Total Summary",
        f"Total Spend: {money(today.spend, currency)}",
        f"Total Purchase: {fmt_number(today.purchase)}",
        f"Total Revenue / Purchase Value: {money(today.revenue, currency)}",
        f"Blended ROAS: {fmt_ratio(today.roas)}",
        f"Blended CPA: {money(today.cpa, currency)}",
        f"Weighted CTR: {fmt_plain_percent(today.ctr)}",
        f"Weighted Frequency: {fmt_number(today.frequency)}",
        f"Total Correct Balance: {fmt_optional_money(total_balance, currency)}",
        f"Estimated Days Remaining: {fmt_optional_days(estimated_days)}",
        "",
    ]


def failure_lines(failure: AccountReportFailure) -> list[str]:
    return [
        "",
        f"账户名称：{failure.account.name}",
        f"Account ID：{failure.account.account_id}",
        f"账户类型：{display_account_type(failure.account)}",
        "数据获取失败",
        f"错误原因：{failure.error_message}",
    ]


def account_section(results: list[AccountReport | AccountReportFailure]) -> list[str]:
    lines = ["B. Account Performance Summary"]
    for result in results:
        if isinstance(result, AccountReportFailure):
            lines.extend(failure_lines(result))
            continue

        report = result
        lines.extend(
            [
                "",
                f"账户名称：{report.account.name}",
                f"账户类型：{display_account_type(report.account)}",
                f"Spend: {money(report.today.spend, report.currency)}",
                f"Purchase: {fmt_number(report.today.purchase)}",
                f"Revenue / Purchase Value: {money(report.today.revenue, report.currency)}",
                f"ROAS: {fmt_ratio(report.today.roas)}",
                f"CPA: {money(report.today.cpa, report.currency)}",
                f"CTR: {fmt_plain_percent(report.today.ctr)}",
                f"Frequency: {fmt_number(report.today.frequency)}",
                f"Correct Balance: {fmt_optional_money(report.correct_balance, report.currency)}",
                f"Estimated Days Remaining: {fmt_optional_days(report.estimated_days_remaining)}",
            ]
        )
    lines.append("")
    return lines


def campaign_section(results: list[AccountReport | AccountReportFailure]) -> list[str]:
    lines = ["C. Campaign Ranking"]
    for result in results:
        if isinstance(result, AccountReportFailure):
            lines.extend(
                [
                    "",
                    result.account.name,
                    f"Account ID: {result.account.account_id}",
                    "数据获取失败",
                    f"错误原因：{result.error_message}",
                ]
            )
            continue

        report = result
        top = sorted(
            report.campaigns,
            key=lambda item: (item[1].roas, item[1].purchase, -item[1].spend),
            reverse=True,
        )[:1]
        bottom = sorted(report.campaigns, key=lambda item: (item[1].roas, item[1].purchase, item[1].spend))[:1]
        lines.extend(["", report.account.name, "Top 1 Campaign"])
        lines.extend(format_campaign_rows(top, report))
        lines.append("Bottom 1 Campaign")
        lines.extend(format_campaign_rows(bottom, report))
    return lines


def format_campaign_rows(campaigns: list[tuple[str, Metrics]], report: AccountReport) -> list[str]:
    if not campaigns:
        return ["No campaign data"]

    rows = []
    for name, metric in campaigns:
        rows.append(
            " | ".join(
                [
                    f"Campaign Name: {name}",
                    f"Spend: {money(metric.spend, report.currency)}",
                    f"Purchase: {fmt_number(metric.purchase)}",
                    f"ROAS: {fmt_ratio(metric.roas)}",
                    f"CPA: {money(metric.cpa, report.currency)}",
                    f"CTR: {fmt_plain_percent(metric.ctr)}",
                    f"Frequency: {fmt_number(metric.frequency)}",
                ]
            )
        )
    return rows
