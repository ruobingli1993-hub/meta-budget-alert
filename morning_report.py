from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from config import ReportAccount
from meta_data_provider import InsightRecord, MetaDataProvider, decimal_or_zero
from meta_api import MetaAPIError, MetaMarketingAPI
from notifier import money


logger = logging.getLogger(__name__)


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


def metric_from_record(record: InsightRecord) -> Metrics:
    if record.data_status == "ERROR":
        raise RuntimeError(record.error or "Meta Data Provider returned ERROR")
    return Metrics(
        spend=decimal_or_zero(record.spend),
        purchase=decimal_or_zero(record.purchase),
        revenue=decimal_or_zero(record.purchase_value),
        clicks=decimal_or_zero(record.clicks),
        impressions=decimal_or_zero(record.impressions),
        reach=decimal_or_zero(record.reach),
    )


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


def log_account_failure(account: ReportAccount, exc: Exception) -> None:
    if isinstance(exc, MetaAPIError):
        logger.error(
            "Morning Report Meta API failed | account_id=%s | HTTP status code=%s | Meta error code=%s | Meta error message=%s",
            account.account_id,
            exc.http_status_code or "unavailable",
            exc.meta_error_code or "unavailable",
            str(exc),
        )
        return

    logger.error(
        "Morning Report Meta API failed | account_id=%s | HTTP status code=unavailable | Meta error code=unavailable | Meta error message=%s",
        account.account_id,
        type(exc).__name__,
    )


def fetch_account_report(api: MetaMarketingAPI, account: ReportAccount) -> AccountReport:
    provider = MetaDataProvider(api)
    meta = provider.get_account_meta(account)
    correct_balance, currency = api.get_spend_limit_balance(account)
    today_record = provider.get_insights(account, "account", "today", meta=meta)[0]
    if today_record.data_status == "ERROR":
        raise RuntimeError(today_record.error or "Today account insights failed")
    today = metric_from_record(today_record)

    last_7d_record = provider.get_insights(account, "account", "last_7_complete_days", meta=meta)[0]
    if last_7d_record.data_status == "ERROR":
        raise RuntimeError(last_7d_record.error or "Last 7 complete days account insights failed")
    last_7d_avg = metric_from_record(last_7d_record).daily_average(7)

    campaign_records = provider.get_insights(account, "campaign", "today", meta=meta)
    campaign_errors = [record for record in campaign_records if record.data_status == "ERROR"]
    if campaign_errors:
        raise RuntimeError(campaign_errors[0].error or "Today campaign insights failed")
    campaigns = [(record.entity_name, metric_from_record(record)) for record in campaign_records if record.data_status == "SUCCESS"]
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
            log_account_failure(account, exc)
            results.append(AccountReportFailure(account=account, error_message=sanitize_error(exc)))

    reports = [result for result in results if isinstance(result, AccountReport)]
    failures = [result for result in results if isinstance(result, AccountReportFailure)]
    if len(failures) == len(accounts):
        return build_all_failed_report(failures)

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


def build_all_failed_report(failures: list[AccountReportFailure]) -> str:
    lines = [
        "⚠️ Meta Morning Report 数据获取失败",
        "",
        "所有账户 Meta API 请求失败，本次报告不可用于判断投放表现。",
        "",
        "失败账户：",
    ]
    for failure in failures:
        lines.extend(
            [
                "",
                f"账户名称：{failure.account.name}",
                f"Account ID：{failure.account.account_id}",
                "数据获取失败",
                f"错误原因：{failure.error_message}",
            ]
        )
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
