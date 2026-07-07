from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from config import ReportAccount
from meta_api import MetaMarketingAPI
from notifier import money


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
    balance: Decimal
    today: Metrics
    last_7d_avg: Metrics
    last_30d_avg: Metrics
    campaigns: list[tuple[str, Metrics]]

    @property
    def estimated_days_remaining(self) -> Decimal:
        return safe_div(self.balance, self.last_7d_avg.spend)


def safe_div(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def metric_from_rows(rows: list[dict[str, Any]]) -> Metrics:
    total = Metrics()
    for row in rows:
        total = Metrics(
            spend=total.spend + as_decimal(row.get("spend")),
            purchase=total.purchase + extract_action_value(row.get("actions", [])),
            revenue=total.revenue + extract_action_value(row.get("action_values", [])),
            clicks=total.clicks + as_decimal(row.get("clicks")),
            impressions=total.impressions + as_decimal(row.get("impressions")),
            reach=total.reach + as_decimal(row.get("reach")),
        )
    return total


def extract_action_value(actions: list[dict[str, Any]]) -> Decimal:
    by_type = {str(row.get("action_type")): as_decimal(row.get("value")) for row in actions}
    for action_type in PURCHASE_ACTION_TYPES:
        if action_type in by_type:
            return by_type[action_type]
    return Decimal("0")


def campaign_metrics_from_rows(rows: list[dict[str, Any]]) -> list[tuple[str, Metrics]]:
    campaigns: list[tuple[str, Metrics]] = []
    for row in rows:
        name = str(row.get("campaign_name") or row.get("campaign_id") or "Unknown Campaign")
        campaigns.append((name, metric_from_rows([row])))
    return campaigns


def percent_change(current: Decimal, baseline: Decimal) -> Decimal | None:
    if baseline == 0:
        return None
    return ((current - baseline) / baseline) * Decimal("100")


def fmt_percent(value: Decimal | None) -> str:
    if value is None:
        return "N/A"
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded}%"


def fmt_number(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def fmt_ratio(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.00"), rounding=ROUND_HALF_UP))


def fmt_ctr(value: Decimal) -> str:
    return fmt_percent(value * Decimal("100"))


def fetch_account_report(api: MetaMarketingAPI, account: ReportAccount) -> AccountReport:
    balance, currency = api.get_account_balance(account)
    today = metric_from_rows(api.get_account_insights(account, "today"))
    last_7d = metric_from_rows(api.get_account_insights(account, "last_7d")).daily_average(7)
    last_30d = metric_from_rows(api.get_account_insights(account, "last_30d")).daily_average(30)
    campaigns = campaign_metrics_from_rows(api.get_campaign_insights(account, "today"))
    return AccountReport(
        account=account,
        currency=currency,
        balance=balance,
        today=today,
        last_7d_avg=last_7d,
        last_30d_avg=last_30d,
        campaigns=campaigns,
    )


def display_account_type(account: ReportAccount) -> str:
    if account.account_type == "brand":
        return "Brand Account"
    return "Performance Account"


def build_morning_report(accounts: list[ReportAccount], api: MetaMarketingAPI) -> str:
    if len(accounts) != 3:
        raise ValueError(
            "Morning Report V1 requires exactly 3 report accounts. Configure MORNING_REPORT_ACCOUNTS_JSON "
            "or JELENEW_BRAND_ACCOUNT_ID."
        )

    reports = [fetch_account_report(api, account) for account in accounts]
    currency = reports[0].currency if reports else "USD"
    overall_today = combine_metrics([report.today for report in reports])
    overall_7d = combine_metrics([report.last_7d_avg for report in reports])
    overall_30d = combine_metrics([report.last_30d_avg for report in reports])
    total_balance = sum((report.balance for report in reports), Decimal("0"))
    days_remaining = safe_div(total_balance, overall_7d.spend)

    lines: list[str] = ["Morning Report V1", ""]
    lines.extend(overall_section(overall_today, overall_7d, overall_30d, total_balance, days_remaining, currency))
    lines.extend(account_section(reports))
    lines.extend(campaign_section(reports))
    lines.extend(health_section(reports, overall_today, overall_7d, overall_30d, total_balance, days_remaining, currency))
    lines.extend(observation_section(reports, overall_today, overall_7d, overall_30d))
    return "\n".join(lines)


def combine_metrics(metrics: list[Metrics]) -> Metrics:
    return Metrics(
        spend=sum((metric.spend for metric in metrics), Decimal("0")),
        purchase=sum((metric.purchase for metric in metrics), Decimal("0")),
        revenue=sum((metric.revenue for metric in metrics), Decimal("0")),
        clicks=sum((metric.clicks for metric in metrics), Decimal("0")),
        impressions=sum((metric.impressions for metric in metrics), Decimal("0")),
        reach=sum((metric.reach for metric in metrics), Decimal("0")),
    )


def overall_section(
    today: Metrics,
    avg_7d: Metrics,
    avg_30d: Metrics,
    balance: Decimal,
    days_remaining: Decimal,
    currency: str,
) -> list[str]:
    return [
        "1. Overall Total Summary",
        f"Total Spend: {money(today.spend, currency)}",
        f"Total Purchase: {fmt_number(today.purchase)}",
        f"Total Revenue / Purchase Value: {money(today.revenue, currency)}",
        f"Blended ROAS: {fmt_ratio(today.roas)}",
        f"Blended CPA: {money(today.cpa, currency)}",
        f"Weighted CTR: {fmt_ctr(today.ctr)}",
        f"Weighted Frequency: {fmt_number(today.frequency)}",
        f"Total Current Balance: {money(balance, currency)}",
        f"Estimated Days Remaining: {fmt_number(days_remaining)}",
        "",
        f"Spend vs 7D Avg: {fmt_percent(percent_change(today.spend, avg_7d.spend))}",
        f"Spend vs 30D Avg: {fmt_percent(percent_change(today.spend, avg_30d.spend))}",
        f"ROAS vs 7D Avg: {fmt_percent(percent_change(today.roas, avg_7d.roas))}",
        f"ROAS vs 30D Avg: {fmt_percent(percent_change(today.roas, avg_30d.roas))}",
        f"CTR vs 7D Avg: {fmt_percent(percent_change(today.ctr, avg_7d.ctr))}",
        f"CTR vs 30D Avg: {fmt_percent(percent_change(today.ctr, avg_30d.ctr))}",
        f"Frequency vs 7D Avg: {fmt_percent(percent_change(today.frequency, avg_7d.frequency))}",
        f"Frequency vs 30D Avg: {fmt_percent(percent_change(today.frequency, avg_30d.frequency))}",
        "",
    ]


def account_section(reports: list[AccountReport]) -> list[str]:
    lines = ["2. Account Performance Summary"]
    for report in reports:
        summary = classify_account(report)
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
                f"CTR: {fmt_ctr(report.today.ctr)}",
                f"Frequency: {fmt_number(report.today.frequency)}",
                f"Balance: {money(report.balance, report.currency)}",
                f"Estimated Days Remaining: {fmt_number(report.estimated_days_remaining)}",
                f"Spend vs 7D Avg: {fmt_percent(percent_change(report.today.spend, report.last_7d_avg.spend))}",
                f"Spend vs 30D Avg: {fmt_percent(percent_change(report.today.spend, report.last_30d_avg.spend))}",
                f"ROAS vs 7D Avg: {fmt_percent(percent_change(report.today.roas, report.last_7d_avg.roas))}",
                f"ROAS vs 30D Avg: {fmt_percent(percent_change(report.today.roas, report.last_30d_avg.roas))}",
                f"CTR vs 7D Avg: {fmt_percent(percent_change(report.today.ctr, report.last_7d_avg.ctr))}",
                f"CTR vs 30D Avg: {fmt_percent(percent_change(report.today.ctr, report.last_30d_avg.ctr))}",
                summary,
            ]
        )
    lines.append("")
    return lines


def campaign_section(reports: list[AccountReport]) -> list[str]:
    lines = ["3. Campaign Ranking"]
    for report in reports:
        ranked = sorted(report.campaigns, key=lambda item: (item[1].roas, item[1].purchase, -item[1].spend), reverse=True)
        bottom = sorted(report.campaigns, key=lambda item: (item[1].roas, item[1].purchase, item[1].spend))
        lines.extend(["", report.account.name, "Top 5 Campaign"])
        lines.extend(format_campaign_rows(ranked[:5], report))
        lines.append("Bottom 5 Campaign")
        lines.extend(format_campaign_rows(bottom[:5], report))
    lines.append("")
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
                    f"CTR: {fmt_ctr(metric.ctr)}",
                    f"Frequency: {fmt_number(metric.frequency)}",
                    f"Action: {campaign_action(metric, report)}",
                ]
            )
        )
    return rows


def campaign_action(metric: Metrics, report: AccountReport) -> str:
    if metric.spend > report.last_7d_avg.spend * Decimal("0.3") and metric.purchase == 0:
        return "🔴 Urgent Review"
    if report.last_30d_avg.roas and metric.roas < report.last_30d_avg.roas * Decimal("0.8"):
        return "🔴 Urgent Review"
    if report.last_30d_avg.ctr and metric.ctr < report.last_30d_avg.ctr * Decimal("0.9"):
        return "🟡 Review"
    return "🟢 Keep"


def health_section(
    reports: list[AccountReport],
    today: Metrics,
    avg_7d: Metrics,
    avg_30d: Metrics,
    balance: Decimal,
    days_remaining: Decimal,
    currency: str,
) -> list[str]:
    lines = ["4. Health & Anomaly Summary", "", "【Overall Health】", classify_overall(today, avg_7d, avg_30d)]
    lines.extend(["", "【Account Health】"])
    for report in reports:
        lines.append(f"{report.account.name}：{classify_account(report)}")
    lines.extend(["", "【Main Anomalies】"])
    anomalies = collect_anomalies(reports, today, avg_7d, avg_30d, balance, days_remaining, currency)
    lines.extend(anomalies[:5] or ["No major anomaly found."])
    lines.append("")
    return lines


def classify_overall(today: Metrics, avg_7d: Metrics, avg_30d: Metrics) -> str:
    if today.roas < avg_30d.roas * Decimal("0.8") and today.cpa > avg_30d.cpa * Decimal("1.2"):
        return "🔴 Risk：整体 ROAS 低于 30D 超过 20%，且 CPA 上升超过 20%。"
    if today.spend > avg_7d.spend and today.roas < avg_7d.roas:
        return "🟡 Mixed：整体 Spend 上升，但 ROAS 低于 7D，需要观察。"
    return "🟢 Overall healthy：整体 ROAS 高于 30D 或接近历史水平，CPA 稳定，CTR 无明显下滑。"


def classify_account(report: AccountReport) -> str:
    today = report.today
    avg_7d = report.last_7d_avg
    avg_30d = report.last_30d_avg
    if report.account.account_type == "brand":
        if today.ctr < avg_30d.ctr * Decimal("0.8") and today.frequency > avg_30d.frequency * Decimal("1.3"):
            return "🔴 异常：CTR 下降超过 20%，Frequency 上升超过 30%，广告吸引力可能下降。"
        if today.ctr < avg_30d.ctr * Decimal("0.9") or today.frequency > avg_30d.frequency * Decimal("1.2"):
            return "🟡 观察：CTR 低于 30D，或 Frequency 开始上升。"
        return "🟢 健康：CTR 高于或接近 30D，Frequency 稳定。"

    if (
        today.roas < avg_30d.roas * Decimal("0.8")
        or today.cpa > avg_30d.cpa * Decimal("1.2")
        or (today.spend > avg_7d.spend * Decimal("1.3") and today.purchase <= avg_7d.purchase)
    ):
        return "🔴 异常：ROAS 低于 30D 超过 20%，或 CPA 上升超过 20%。"
    if (
        today.roas < avg_30d.roas * Decimal("0.9")
        or today.cpa > avg_30d.cpa * Decimal("1.1")
        or today.ctr < avg_30d.ctr * Decimal("0.9")
    ):
        return "🟡 观察：ROAS、CPA 或 CTR 接近风险区间，需要观察。"
    return "🟢 健康：ROAS 高于或接近 30D，CPA 和 CTR 稳定。"


def collect_anomalies(
    reports: list[AccountReport],
    today: Metrics,
    avg_7d: Metrics,
    avg_30d: Metrics,
    balance: Decimal,
    days_remaining: Decimal,
    currency: str,
) -> list[str]:
    anomalies: list[str] = []
    if today.roas < avg_30d.roas * Decimal("0.8"):
        anomalies.append(f"Overall：ROAS vs 30D Avg {fmt_percent(percent_change(today.roas, avg_30d.roas))}.")
    if today.cpa > avg_30d.cpa * Decimal("1.2"):
        anomalies.append(f"Overall：CPA vs 30D Avg {fmt_percent(percent_change(today.cpa, avg_30d.cpa))}.")
    if today.spend > avg_7d.spend * Decimal("1.3") and today.purchase <= avg_7d.purchase:
        anomalies.append("Overall：Spend 高于 7D Avg 超过 30%，但 Purchase 没有增长。")
    if today.ctr < avg_30d.ctr * Decimal("0.8"):
        anomalies.append(f"Overall：CTR vs 30D Avg {fmt_percent(percent_change(today.ctr, avg_30d.ctr))}.")
    if today.frequency > avg_30d.frequency * Decimal("1.3"):
        anomalies.append(f"Overall：Frequency vs 30D Avg {fmt_percent(percent_change(today.frequency, avg_30d.frequency))}.")
    if days_remaining < Decimal("3"):
        anomalies.append(f"Overall：余额 {money(balance, currency)} 预计不足 3 天。")

    for report in reports:
        if report.account.account_type == "brand" and (
            report.today.ctr < report.last_30d_avg.ctr * Decimal("0.8")
            and report.today.frequency > report.last_30d_avg.frequency * Decimal("1.3")
        ):
            anomalies.append(f"{report.account.name}：Brand Account 吸引力下降。")
    return anomalies


def observation_section(
    reports: list[AccountReport],
    today: Metrics,
    avg_7d: Metrics,
    avg_30d: Metrics,
) -> list[str]:
    observations: list[tuple[str, str, str, str]] = []
    if today.roas < avg_30d.roas:
        observations.append(("Overall", f"整体 ROAS 比 30D 平均低 {fmt_percent(percent_change(today.roas, avg_30d.roas))}。", "30D Avg", "今天重点检查低 ROAS Campaign。"))
    if today.spend > avg_7d.spend and today.purchase <= avg_7d.purchase:
        observations.append(("Overall", "Spend 高于 7D 平均，但 Purchase 未同步增长。", "7D Avg", "观察是否存在预算消耗过快。"))
    for report in reports:
        if report.account.account_type == "brand" and report.today.ctr < report.last_30d_avg.ctr:
            observations.append((report.account.name, f"CTR 比 30D 平均低 {fmt_percent(percent_change(report.today.ctr, report.last_30d_avg.ctr))}，Frequency 比 30D 高 {fmt_percent(percent_change(report.today.frequency, report.last_30d_avg.frequency))}。", "30D Avg", "检查 Brand 素材疲劳。"))
        elif report.today.spend > report.last_7d_avg.spend and report.today.purchase <= report.last_7d_avg.purchase:
            observations.append((report.account.name, "Spend 比 7D 平均高，但 Purchase 基本持平。", "7D Avg", "观察是否存在预算消耗过快。"))

    lines = ["5. Today's Observation"]
    for index, (target, finding, baseline, action) in enumerate(observations[:5], start=1):
        lines.extend(["", f"{index}.", f"对象：{target}", f"观察：{finding}", f"对比基准：{baseline}", f"建议：{action}"])
    if not observations:
        lines.append("No urgent observation today.")
    return lines
