from __future__ import annotations

"""Google Ads 只读日报 V2

读取 Google Ads 指定日期的账户级与口径级指标（花费 / 转化 / 转化价值 / ROAS），
按业务口径（品牌 / 非品牌 × Campaign 类型）汇总，对照当日延迟修正门槛做达标判断，
并通过飞书 Webhook 发送日报。

V2 变更（2026-10-14 用户确认）：
- 不再输出 Campaign 明细，改为「品牌 / 非品牌 × 类型」口径汇总；
- Cycling-1 为养户账户：仅报花费，不报转化、不参与 ROI 判断。

安全边界：
- 全程只读，绝不执行任何预算 / 出价 / 广告写操作；
- 凭据仅从 .env 读取，不写入日志与输出；
- 默认 dry-run 打印，加 --send 才发送飞书。
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Google Ads 凭据与账户配置（只读自 .env）
# ---------------------------------------------------------------------------

GOOGLE_ADS_DEVELOPER_TOKEN = os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", "")
GOOGLE_ADS_CLIENT_ID = os.getenv("GOOGLE_ADS_CLIENT_ID", "")
GOOGLE_ADS_CLIENT_SECRET = os.getenv("GOOGLE_ADS_CLIENT_SECRET", "")
GOOGLE_ADS_REFRESH_TOKEN = os.getenv("GOOGLE_ADS_REFRESH_TOKEN", "")
GOOGLE_ADS_LOGIN_CUSTOMER_ID = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "")

# 广告账户 ID 列表（MCC 下的具体投放账户）
GOOGLE_ADS_CUSTOMER_IDS: list[str] = [
    cid.strip()
    for cid in os.getenv("GOOGLE_ADS_CUSTOMER_IDS", "").split(",")
    if cid.strip()
]

GOOGLE_ACCOUNT_NAMES = {
    "8385977843": "jelenew-Q&M",
    "5188331105": "Jelenew Cycling-1",
}

# 养户账户：仅报花费，不报转化 / 不参与 ROI 判断
SPEND_ONLY_ACCOUNTS = {"5188331105"}

# 业务口径（来自项目文档 GOOGLE_AUTOMATION_PROJECT.md §4）
DELAY_FACTOR_3 = Decimal("1.3")
DELAY_FACTOR_7 = Decimal("1.44")
TARGET_ROAS_NONBRAND = Decimal("1.35")   # search/shopping/pmax，不含 brand
TARGET_ROAS_BRAND = Decimal("6")         # search 且含 brand

# 窗口相对 7 天目标的系数：窗口门槛 = 7天目标 × factor
WINDOW_FACTORS: list[tuple[str, Decimal]] = [
    ("当天", Decimal("1") / DELAY_FACTOR_7),
    ("3天", DELAY_FACTOR_3 / DELAY_FACTOR_7),
    ("7天", Decimal("1")),
]

# 广告类型枚举（Google Ads API）
SEARCH_TYPE = "SEARCH"
SHOPPING_TYPE = "SHOPPING"
PMAX_TYPE = "PERFORMANCE_MAX"
NONBRAND_TYPES = {SEARCH_TYPE, SHOPPING_TYPE, PMAX_TYPE}


@dataclass(frozen=True)
class CampaignDaily:
    campaign_id: str
    name: str
    campaign_type: str
    spend: Decimal
    conversions: Decimal
    conversion_value: Decimal
    roas: Decimal
    target_roas: Decimal | None
    daily_threshold: Decimal | None
    is_brand: bool
    within_scope: bool
    status_ok: bool | None  # None = 不在口径范围


@dataclass(frozen=True)
class BucketDaily:
    """口径汇总桶：品牌 / 非品牌 × Campaign 类型。"""
    bucket_key: str
    is_brand: bool
    campaign_type: str
    spend: Decimal
    conversions: Decimal
    conversion_value: Decimal
    target_roas: Decimal | None
    daily_threshold: Decimal | None
    within_scope: bool

    @property
    def roas(self) -> Decimal:
        return safe_div(self.conversion_value, self.spend)

    @property
    def status_ok(self) -> bool | None:
        if not self.within_scope or self.daily_threshold is None:
            return None
        return self.roas >= self.daily_threshold


@dataclass(frozen=True)
class PeriodSummary:
    """某段时间的汇总指标（仅指标账户，不含养户）。"""
    spend: Decimal
    conversions: Decimal
    conversion_value: Decimal

    @property
    def roas(self) -> Decimal:
        return safe_div(self.conversion_value, self.spend)

    @property
    def roas(self) -> Decimal:
        return safe_div(self.conversion_value, self.spend)

    @property
    def status_ok(self) -> bool | None:
        if not self.within_scope or self.daily_threshold is None:
            return None
        return self.roas >= self.daily_threshold


def safe_div(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator


def micros_to_dollars(micros) -> Decimal:
    try:
        return Decimal(int(micros)) / Decimal("1000000")
    except (TypeError, ValueError):
        return Decimal("0")


def to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError):
        return Decimal("0")


def classify_campaign(campaign_type: str, campaign_name: str) -> tuple[Decimal, bool, bool]:
    """返回 (目标 ROAS, 是否品牌, 是否在口径范围内)。"""
    name = (campaign_name or "").lower()
    is_brand = "brand" in name
    if campaign_type == SEARCH_TYPE and is_brand:
        return TARGET_ROAS_BRAND, True, True
    if campaign_type in NONBRAND_TYPES and not is_brand:
        return TARGET_ROAS_NONBRAND, False, True
    return Decimal("0"), is_brand, False


def daily_threshold(target_roas: Decimal) -> Decimal:
    """当日（D1）达标门槛 = 目标 ÷ 延迟因子 7。"""
    return target_roas / DELAY_FACTOR_7


def build_google_config() -> dict:
    missing = [
        key
        for key, value in {
            "GOOGLE_ADS_DEVELOPER_TOKEN": GOOGLE_ADS_DEVELOPER_TOKEN,
            "GOOGLE_ADS_CLIENT_ID": GOOGLE_ADS_CLIENT_ID,
            "GOOGLE_ADS_CLIENT_SECRET": GOOGLE_ADS_CLIENT_SECRET,
            "GOOGLE_ADS_REFRESH_TOKEN": GOOGLE_ADS_REFRESH_TOKEN,
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": GOOGLE_ADS_LOGIN_CUSTOMER_ID,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing Google Ads environment variables: {', '.join(missing)}")
    return {
        "developer_token": GOOGLE_ADS_DEVELOPER_TOKEN,
        "client_id": GOOGLE_ADS_CLIENT_ID,
        "client_secret": GOOGLE_ADS_CLIENT_SECRET,
        "refresh_token": GOOGLE_ADS_REFRESH_TOKEN,
        "login_customer_id": GOOGLE_ADS_LOGIN_CUSTOMER_ID,
        "use_proto_plus": True,
    }


def fetch_account_daily(client, customer_id: str, date_str: str) -> list[CampaignDaily]:
    """读取单账户指定日期 Campaign 级数据。"""
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign.advertising_channel_type,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value
        FROM campaign
        WHERE segments.date = '{date_str}'
        ORDER BY metrics.cost_micros DESC
    """
    campaigns: list[CampaignDaily] = []
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in stream:
        for row in batch.results:
            campaign_type = str(row.campaign.advertising_channel_type.name)
            spend = micros_to_dollars(row.metrics.cost_micros)
            conversions = to_decimal(row.metrics.conversions)
            conversion_value = to_decimal(row.metrics.conversions_value)
            roas = safe_div(conversion_value, spend)
            target, is_brand, within_scope = classify_campaign(campaign_type, row.campaign.name)
            threshold = daily_threshold(target) if within_scope else None
            status_ok = roas >= threshold if within_scope else None
            campaigns.append(
                CampaignDaily(
                    campaign_id=str(row.campaign.id),
                    name=row.campaign.name,
                    campaign_type=campaign_type,
                    spend=spend,
                    conversions=conversions,
                    conversion_value=conversion_value,
                    roas=roas,
                    target_roas=target if within_scope else None,
                    daily_threshold=threshold,
                    is_brand=is_brand,
                    within_scope=within_scope,
                    status_ok=status_ok,
                )
            )
    return campaigns


def fetch_account_range(
    client, customer_id: str, start_date: str, end_date: str
) -> dict[str, PeriodSummary]:
    """拉指定日期范围内账户级汇总（不含养户账户），返回 {date_str: PeriodSummary}。"""
    if customer_id in SPEND_ONLY_ACCOUNTS:
        return {}
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          segments.date,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY segments.date
    """
    by_day: dict[str, PeriodSummary] = {}
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in stream:
        for row in batch.results:
            day = str(row.segments.date)
            spend = micros_to_dollars(row.metrics.cost_micros)
            conv = to_decimal(row.metrics.conversions)
            value = to_decimal(row.metrics.conversions_value)
            existing = by_day.get(day)
            if existing is None:
                by_day[day] = PeriodSummary(spend=spend, conversions=conv, conversion_value=value)
            else:
                by_day[day] = PeriodSummary(
                    spend=existing.spend + spend,
                    conversions=existing.conversions + conv,
                    conversion_value=existing.conversion_value + value,
                )
    return by_day


def fetch_hourly_spend(client, customer_id: str, date_str: str) -> dict[int, Decimal]:
    """拉某一天的小时级花费，返回 {hour: spend}（小时为账户时区 0-23）。"""
    if customer_id in SPEND_ONLY_ACCOUNTS:
        return {}
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
          segments.hour,
          metrics.cost_micros
        FROM campaign
        WHERE segments.date = '{date_str}'
        ORDER BY segments.hour
    """
    by_hour: dict[int, Decimal] = {}
    stream = ga_service.search_stream(customer_id=customer_id, query=query)
    for batch in stream:
        for row in batch.results:
            hour = int(row.segments.hour)
            spend = micros_to_dollars(row.metrics.cost_micros)
            by_hour[hour] = by_hour.get(hour, Decimal("0")) + spend
    return by_hour


def bucket_label(is_brand: bool, campaign_type: str) -> str:
    brand_mark = "Brand" if is_brand else "NonBrand"
    return f"{brand_mark} · {campaign_type}"


def bucket_key(is_brand: bool, campaign_type: str) -> str:
    return f"{'B' if is_brand else 'N'}:{campaign_type}"


def fmt_money(value: Decimal) -> str:
    return f"${value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"


def fmt_number(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_report_text(
    results: list[tuple[str, list[CampaignDaily]]],
    failures: list[tuple[str, str]],
    date_str: str,
    today_spend: Decimal = Decimal("0"),
    yesterday_summary: PeriodSummary | None = None,
    three_day_summary: PeriodSummary | None = None,
    seven_day_summary: PeriodSummary | None = None,
) -> str:
    lines: list[str] = [f"Google Ads 日报 | {date_str}", ""]

    if failures:
        lines.append("⚠️ 部分账户获取失败：")
        for account_id, error in failures:
            lines.append(f"  {GOOGLE_ACCOUNT_NAMES.get(account_id, account_id)}：{error}")
        lines.append("")

    # ---- 账户花费 ----
    lines.append("账户花费")
    total_spend = Decimal("0")
    for account_id, campaigns in results:
        spend = sum((c.spend for c in campaigns), Decimal("0"))
        total_spend += spend
        name = GOOGLE_ACCOUNT_NAMES.get(account_id, account_id)
        if account_id in SPEND_ONLY_ACCOUNTS:
            lines.append(f"  {name}：{fmt_money(spend)}（养户，仅花费）")
        else:
            lines.append(f"  {name}：{fmt_money(spend)}")
    lines.append(f"  合计：{fmt_money(total_spend)}")

    # ---- 花费环比 + ROI 达标对比 ----
    yesterday_summary = yesterday_summary or PeriodSummary(Decimal("0"), Decimal("0"), Decimal("0"))
    three_day_summary = three_day_summary or PeriodSummary(Decimal("0"), Decimal("0"), Decimal("0"))
    seven_day_summary = seven_day_summary or PeriodSummary(Decimal("0"), Decimal("0"), Decimal("0"))

    if yesterday_summary.spend > 0:
        delta = (today_spend - yesterday_summary.spend) / yesterday_summary.spend * 100
        sign = "+" if delta >= 0 else ""
        lines.append(f"  花费对比昨天：{sign}{delta.quantize(Decimal('0.1'))}%")
    else:
        lines.append("  花费对比昨天：N/A（昨日无数据）")

    # 加权门槛（和下面"账户加权目标"同一套口径）
    metric_accounts = [(aid, c) for aid, c in results if aid not in SPEND_ONLY_ACCOUNTS]
    scope_spend = Decimal("0")
    scope_value = Decimal("0")
    weighted_numerator_d1 = Decimal("0")
    weighted_numerator_d3 = Decimal("0")
    weighted_numerator_d7 = Decimal("0")
    for _aid, campaigns in metric_accounts:
        for c in campaigns:
            if c.within_scope and c.target_roas is not None:
                scope_spend += c.spend
                scope_value += c.conversion_value
                weighted_numerator_d1 += c.spend * c.target_roas * (Decimal("1") / DELAY_FACTOR_7)
                weighted_numerator_d3 += c.spend * c.target_roas * (DELAY_FACTOR_3 / DELAY_FACTOR_7)
                weighted_numerator_d7 += c.spend * c.target_roas * Decimal("1")

    def _ok_mark(actual: Decimal, threshold: Decimal) -> str:
        if threshold == 0:
            return "—"
        return "✅" if actual >= threshold else "⛔"

    if scope_spend > 0:
        d1_threshold = weighted_numerator_d1 / scope_spend
        d3_threshold = weighted_numerator_d3 / scope_spend
        d7_threshold = weighted_numerator_d7 / scope_spend
        today_roas = safe_div(scope_value, scope_spend)
        lines.append(f"  当天 ROI：{fmt_number(today_roas)}（门槛 {fmt_number(d1_threshold)}）{_ok_mark(today_roas, d1_threshold)}")
        lines.append(f"  近3天 ROI：{fmt_number(three_day_summary.roas)}（门槛 {fmt_number(d3_threshold)}）{_ok_mark(three_day_summary.roas, d3_threshold)}")
        lines.append(f"  近7天 ROI：{fmt_number(seven_day_summary.roas)}（门槛 {fmt_number(d7_threshold)}）{_ok_mark(seven_day_summary.roas, d7_threshold)}")
    lines.append("")

    # ---- 口径汇总（仅指标账户，跨账户合并）----
    metric_accounts = [
        (account_id, campaigns)
        for account_id, campaigns in results
        if account_id not in SPEND_ONLY_ACCOUNTS
    ]
    buckets: dict[str, BucketDaily] = {}
    other_spend = Decimal("0")
    other_conv = Decimal("0")
    other_value = Decimal("0")
    for _account_id, campaigns in metric_accounts:
        for campaign in campaigns:
            if campaign.within_scope:
                key = bucket_key(campaign.is_brand, campaign.campaign_type)
                existing = buckets.get(key)
                if existing is None:
                    buckets[key] = BucketDaily(
                        bucket_key=key,
                        is_brand=campaign.is_brand,
                        campaign_type=campaign.campaign_type,
                        spend=campaign.spend,
                        conversions=campaign.conversions,
                        conversion_value=campaign.conversion_value,
                        target_roas=campaign.target_roas,
                        daily_threshold=campaign.daily_threshold,
                        within_scope=True,
                    )
                else:
                    buckets[key] = BucketDaily(
                        bucket_key=key,
                        is_brand=existing.is_brand,
                        campaign_type=existing.campaign_type,
                        spend=existing.spend + campaign.spend,
                        conversions=existing.conversions + campaign.conversions,
                        conversion_value=existing.conversion_value + campaign.conversion_value,
                        target_roas=existing.target_roas,
                        daily_threshold=existing.daily_threshold,
                        within_scope=True,
                    )
            else:
                other_spend += campaign.spend
                other_conv += campaign.conversions
                other_value += campaign.conversion_value

    lines.append("口径汇总（7 天目标 → 当日门槛）")
    if not buckets:
        lines.append("  （无口径内数据）")
    else:
        # 固定顺序：NonBrand SEARCH/SHOPPING/PERFORMANCE_MAX → Brand SEARCH
        ordered = [
            (False, SEARCH_TYPE),
            (False, SHOPPING_TYPE),
            (False, PMAX_TYPE),
            (True, SEARCH_TYPE),
        ]
        for is_brand, campaign_type in ordered:
            key = bucket_key(is_brand, campaign_type)
            bucket = buckets.get(key)
            if bucket is None:
                continue
            mark = "✅" if bucket.status_ok else ("⛔" if bucket.status_ok is False else "—")
            lines.append(
                f"  {mark} {bucket_label(is_brand, campaign_type)}："
                f"花费 {fmt_money(bucket.spend)} | 转化 {fmt_number(bucket.conversions)} | "
                f"ROI {fmt_number(bucket.roas)}"
            )
            lines.append(
                f"     目标 {fmt_number(bucket.target_roas)} → 当日门槛 {fmt_number(bucket.daily_threshold)} | "
                f"{'达标' if bucket.status_ok else '未达'}"
            )
    if other_spend > 0:
        lines.append(
            f"  其他（口径外类型）：花费 {fmt_money(other_spend)}（不判断达标）"
        )
    lines.append("")

    # ---- 账户加权目标（按口径内花费占比）----
    lines.append("账户加权目标（按口径内花费占比）")
    bucket_list = list(buckets.values())
    if not bucket_list:
        lines.append("  （无口径内数据，无法加权）")
    else:
        total_scope_spend = sum((b.spend for b in bucket_list), Decimal("0"))
        actual_spend = sum((b.spend for b in bucket_list), Decimal("0"))
        actual_value = sum((b.conversion_value for b in bucket_list), Decimal("0"))
        actual_roas = safe_div(actual_value, actual_spend)

        weighted: list[str] = []
        for window_name, factor in WINDOW_FACTORS:
            numerator = sum(
                (b.spend * b.target_roas * factor for b in bucket_list if b.target_roas is not None),
                Decimal("0"),
            )
            weighted_target = safe_div(numerator, total_scope_spend)
            weighted.append(f"{window_name} {fmt_number(weighted_target)}")
        lines.append(f"  {' | '.join(weighted)}")
        lines.append(f"  账户当天实际 ROI（口径内）：{fmt_number(actual_roas)}")
        if bucket_list:
            d1_factor = WINDOW_FACTORS[0][1]
            d1_weighted = safe_div(
                sum((b.spend * b.target_roas * d1_factor for b in bucket_list if b.target_roas is not None), Decimal("0")),
                total_scope_spend,
            )
            ok = actual_roas >= d1_weighted
            lines.append(f"  对照加权当天门槛 {fmt_number(d1_weighted)}：{'达标 ✅' if ok else '未达 ⛔'}")
        lines.append("")

    lines.append("口径：NonBrand(SEARCH/SHOPPING/PMAX) 目标1.35→门槛0.94；Brand(SEARCH) 目标6→门槛4.17")
    lines.append("养户账户（Cycling-1）不参与 ROI 判断。本日报只读自 Google Ads API，不含写操作。")
    return "\n".join(lines)


def run_daily_report(date_str: str | None = None, label: str | None = None) -> str:
    if not GOOGLE_ADS_CUSTOMER_IDS:
        raise RuntimeError("GOOGLE_ADS_CUSTOMER_IDS is empty; check .env")

    report_date = date_str or (date.today() - timedelta(days=1)).isoformat()
    report_label = label or report_date
    config = build_google_config()

    from google.ads.googleads.client import GoogleAdsClient

    client = GoogleAdsClient.load_from_dict(config)

    results: list[tuple[str, list[CampaignDaily]]] = []
    failures: list[tuple[str, str]] = []
    for customer_id in GOOGLE_ADS_CUSTOMER_IDS:
        try:
            campaigns = fetch_account_daily(client, customer_id, report_date)
            results.append((customer_id, campaigns))
        except Exception as exc:  # 单账户失败不阻塞整体
            failures.append((customer_id, f"{type(exc).__name__}: {exc}"))
            logger.error("Google daily report failed | account=%s | error=%s", customer_id, exc)

    # 拉近 7 天完整日数据，用于 3/7 天 ROI 对比
    report_dt = date.fromisoformat(report_date)
    range_start = (report_dt - timedelta(days=7)).isoformat()
    range_end = (report_dt - timedelta(days=1)).isoformat()
    by_day: dict[str, PeriodSummary] = {}
    for customer_id in GOOGLE_ADS_CUSTOMER_IDS:
        try:
            for day, summary in fetch_account_range(client, customer_id, range_start, range_end).items():
                existing = by_day.get(day)
                if existing is None:
                    by_day[day] = summary
                else:
                    by_day[day] = PeriodSummary(
                        spend=existing.spend + summary.spend,
                        conversions=existing.conversions + summary.conversions,
                        conversion_value=existing.conversion_value + summary.conversion_value,
                    )
        except Exception as exc:
            logger.warning("Range fetch failed for account %s: %s", customer_id, exc)

    def _sum_days(days: list[str]) -> PeriodSummary:
        spend = Decimal("0")
        conv = Decimal("0")
        value = Decimal("0")
        for d in days:
            s = by_day.get(d)
            if s:
                spend += s.spend
                conv += s.conversions
                value += s.conversion_value
        return PeriodSummary(spend=spend, conversions=conv, conversion_value=value)

    yesterday = (report_dt - timedelta(days=1)).isoformat()
    day_before = (report_dt - timedelta(days=2)).isoformat()
    three_days = [yesterday, day_before, (report_dt - timedelta(days=3)).isoformat()]
    seven_days = [(report_dt - timedelta(days=i)).isoformat() for i in range(1, 8)]

    # 同时段对比：今天到现在的花费 vs 昨天同时段花费
    today_hourly: dict[int, Decimal] = {}
    yesterday_hourly: dict[int, Decimal] = {}
    for customer_id in GOOGLE_ADS_CUSTOMER_IDS:
        try:
            for h, s in fetch_hourly_spend(client, customer_id, report_date).items():
                today_hourly[h] = today_hourly.get(h, Decimal("0")) + s
        except Exception as exc:
            logger.warning("Hourly fetch failed for today, account %s: %s", customer_id, exc)
        try:
            for h, s in fetch_hourly_spend(client, customer_id, yesterday).items():
                yesterday_hourly[h] = yesterday_hourly.get(h, Decimal("0")) + s
        except Exception as exc:
            logger.warning("Hourly fetch failed for yesterday, account %s: %s", customer_id, exc)

    today_spend = sum(today_hourly.values(), Decimal("0"))
    # 昨天只取到今天已经过的小时数为止（同时段对比）
    max_hour_today = max(today_hourly.keys()) if today_hourly else 0
    yesterday_same_window_spend = sum(
        s for h, s in yesterday_hourly.items() if h <= max_hour_today
    )
    yesterday_summary = PeriodSummary(
        spend=yesterday_same_window_spend,
        conversions=Decimal("0"),
        conversion_value=Decimal("0"),
    )
    three_day_summary = _sum_days(three_days)
    seven_day_summary = _sum_days(seven_days)

    return build_report_text(
        results, failures, report_label,
        today_spend=today_spend,
        yesterday_summary=yesterday_summary,
        three_day_summary=three_day_summary,
        seven_day_summary=seven_day_summary,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Google Ads 只读日报")
    parser.add_argument("--date", default=None, help="报表日期 YYYY-MM-DD（默认昨天）")
    parser.add_argument("--today", action="store_true", help="拉取今天实时累计数据（daily-close 用）")
    parser.add_argument("--send", action="store_true", help="发送飞书 Webhook（默认只打印）")
    parser.add_argument("--debug", action="store_true", help="输出 debug 日志")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.today:
        report_date = date.today().isoformat()
        report_label = f"{report_date}（当日累计·实时）"
    else:
        report_date = args.date or (date.today() - timedelta(days=1)).isoformat()
        report_label = report_date
    report = run_daily_report(report_date, label=report_label)
    print(report)

    if args.send:
        if not os.getenv("FEISHU_WEBHOOK_URL"):
            raise RuntimeError("FEISHU_WEBHOOK_URL is empty; cannot send")
        from feishu import FeishuWebhookClient
        delivery = FeishuWebhookClient().send_text(report)
        print(f"\n[Sent] http_status={delivery['http_status']} feishu_code={delivery['feishu_code']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
