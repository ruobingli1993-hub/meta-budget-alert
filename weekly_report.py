from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils.datetime import from_excel

TRUE_GOOGLE_PURCHASE = "Google Shopping App Purchase (2)"
BI_OVERALL_CHANNELS = ("Meta投放流量", "GOOGLE投放流量")
AUDIENCE_MAP = {
    "prospecting": "新客",
    "engaged": "新客",
    "existing": "老客/再营销",
    "uncategorized": "未识别",
    "unknown": "未识别",
}
META_ACCOUNT_TYPES = {
    "QMDT—20240103": "Performance",
    "销售三部—新主页账户": "Performance",
    "Jelenew-Brand & Lab": "Brand",
}
CREATIVE_ACCOUNT_IDS = {"750289240467952", "5600626876733411"}
NA = "N/A"


@dataclass(frozen=True)
class WeeklyPaths:
    bi: Path
    google_performance: Path
    google_conversions: Path
    meta_audience: Path
    meta_country: Path


@dataclass
class WeeklyData:
    overview: list[dict[str, Any]]
    weekly: list[dict[str, Any]]
    month_to_date: list[dict[str, Any]]
    google: list[dict[str, Any]]
    meta_accounts: list[dict[str, Any]]
    audience: list[dict[str, Any]]
    country: list[dict[str, Any]]
    creative: list[dict[str, Any]]
    reviews: dict[str, list[dict[str, Any]]]


def discover_inputs(input_dir: Path) -> WeeklyPaths:
    def one(folder: str, prefix: str) -> Path:
        matches = sorted((input_dir / folder).glob(f"{prefix}*.xlsx"))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one {prefix}*.xlsx under {folder}; found {len(matches)}")
        return matches[0]

    return WeeklyPaths(
        bi=one("01_Raw_Data/BI", "BI_Weekly_"),
        google_performance=one("01_Raw_Data/Google", "Google_Ads_Performance_"),
        google_conversions=one("01_Raw_Data/Google", "Google_Conversion_Actions_"),
        meta_audience=one("01_Raw_Data/Meta", "Meta_AI_受众"),
        meta_country=one("01_Raw_Data/Meta", "Meta_AI_国家"),
    )


def read_rows(path: Path, sheet_index: int = 1, header_row: int = 1) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[sheet_index]
    headers = [cell.value for cell in next(sheet.iter_rows(min_row=header_row, max_row=header_row))]
    rows: list[dict[str, Any]] = []
    for values in sheet.iter_rows(min_row=header_row + 1, values_only=True):
        if not any(value is not None for value in values):
            continue
        rows.append({str(headers[index]): value for index, value in enumerate(values) if index < len(headers) and headers[index] is not None})
    return rows


def as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return from_excel(value).date()
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
    return None


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def total(rows: Iterable[dict[str, Any]], key: str) -> float | None:
    values = [number(row.get(key)) for row in rows]
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def divide(numerator: float | None, denominator: float | None) -> float | str:
    if numerator is None or denominator in (None, 0):
        return NA
    return numerator / denominator


def period_label(start: date, end: date) -> str:
    return f"{start.isoformat()} - {end.isoformat()}"


def bi_metrics(rows: list[dict[str, Any]], start: date, end: date, channel: str) -> dict[str, Any]:
    selected = [row for row in rows if as_date(row.get("event_date(day)")) and start <= as_date(row.get("event_date(day)")) <= end and row.get("来源渠道") == channel]
    spend = total(selected, "营销花费")
    revenue = total(selected, "销售额")
    orders = total(selected, "订单量_双重")
    uv = total(selected, "uv")
    paid_uv = total(selected, "支付uv")
    return {
        "Period Start": start.isoformat(), "Period End": end.isoformat(), "Channel": channel,
        "Spend": spend if spend is not None else NA, "Revenue": revenue if revenue is not None else NA,
        "Orders": orders if orders is not None else NA, "ROI": divide(revenue, spend),
        "CPA": divide(spend, orders), "AOS": divide(revenue, orders), "Payment CVR": divide(paid_uv, uv),
    }


def google_channel(campaign_type: Any, campaign_name: Any) -> str:
    kind = str(campaign_type or "").strip().lower()
    name = str(campaign_name or "").strip().lower()
    if kind == "demand gen":
        return "GOOGLE付费YOUTUBE" if "_brand" in name else "GOOGLE付费探索广告"
    if kind == "shopping":
        return "GOOGLE付费购物广告"
    if kind == "search" and "brand" in name:
        return "GOOGLE付费品牌词"
    if kind == "search" and "product" in name:
        return "GOOGLE付费品类词"
    if kind == "performance max":
        return "GOOGLE付费PMAX"
    return "未识别"


def google_metrics(performance: list[dict[str, Any]], conversions: list[dict[str, Any]], start: date, end: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    purchase_by_key: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {"Purchase": 0.0, "Purchase Value": 0.0})
    unknown_actions: list[dict[str, Any]] = []
    for row in conversions:
        day = as_date(row.get("Day"))
        if day is None or not start <= day <= end:
            continue
        action = str(row.get("Conversion action") or "")
        if action == TRUE_GOOGLE_PURCHASE:
            key = (str(row.get("Customer ID")), str(row.get("Campaign ID")))
            purchase_by_key[key]["Purchase"] += number(row.get("Conversions")) or 0
            purchase_by_key[key]["Purchase Value"] += number(row.get("Conv. value")) or 0
        elif action not in {
            "Google Shopping App Page View (2)", "网页浏览（Google Analytics 事件 view_item）",
            "网页浏览（Google Analytics 事件 浏览时间_1min）", "网页浏览（Google Analytics 事件 进入网站）",
        }:
            unknown_actions.append({"Type": "Unknown Google Conversion", "Value": action, "Status": "Review"})

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    unmatched: list[dict[str, Any]] = []
    for row in performance:
        day = as_date(row.get("Day"))
        if day is None or not start <= day <= end:
            continue
        key = (str(row.get("Customer ID")), str(row.get("Campaign ID")))
        if key not in grouped:
            channel = google_channel(row.get("Campaign type"), row.get("Campaign"))
            grouped[key] = {
                "Customer ID": key[0], "Account": row.get("Account name"), "Campaign ID": key[1],
                "Campaign": row.get("Campaign"), "Campaign Type": row.get("Campaign type"), "BI Channel": channel,
                "Spend": 0.0, "Clicks": 0.0, "Impressions": 0.0,
            }
            if channel == "未识别":
                unmatched.append({"Type": "Unmatched Google Campaign", "Account": row.get("Account name"), "Campaign ID": key[1], "Campaign": row.get("Campaign"), "Status": "Review"})
        grouped[key]["Spend"] += number(row.get("Cost")) or 0
        grouped[key]["Clicks"] += number(row.get("Clicks")) or 0
        grouped[key]["Impressions"] += number(row.get("Impr.")) or 0

    result: list[dict[str, Any]] = []
    for key, row in grouped.items():
        purchase = purchase_by_key.get(key, {"Purchase": 0.0, "Purchase Value": 0.0})
        row.update(purchase)
        row["Purchase CVR"] = divide(purchase["Purchase"], row["Clicks"])
        row["Purchase ROAS"] = divide(purchase["Purchase Value"], row["Spend"])
        result.append(row)
    return sorted(result, key=lambda row: row["Spend"], reverse=True), unknown_actions, unmatched


def meta_sample(rows: list[dict[str, Any]], start: date, end: date, audience: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    label = period_label(start, end)
    selected: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("单周") or "") != label or not row.get("账户名称"):
            continue
        output = dict(row)
        clicks = number(row.get("点击量（全部）"))
        output["Purchase CVR (All Clicks)"] = divide(number(row.get("购物次数")), clicks)
        output["ATC Rate (All Clicks)"] = divide(number(row.get("加入购物车次数")), clicks)
        output["Checkout Rate (All Clicks)"] = divide(number(row.get("结账发起次数")), clicks)
        if audience:
            segment = str(row.get("受众细分") or "unknown").lower()
            output["周报分类"] = AUDIENCE_MAP.get(segment, "未识别")
            if segment not in AUDIENCE_MAP or output["周报分类"] == "未识别":
                reviews.append({"Type": "Unrecognized Meta Audience", "Account": row.get("账户名称"), "Value": segment, "Status": "Review"})
        selected.append(output)
    return selected, reviews


def meta_account_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for account_name, account_type in META_ACCOUNT_TYPES.items():
        selected = [row for row in rows if row.get("账户名称") == account_name]
        spend = total(selected, "已花费金额 (USD)")
        purchase = total(selected, "购物次数")
        revenue = total(selected, "购物转化价值")
        impressions = total(selected, "展示次数")
        reach = total(selected, "覆盖人数")
        clicks = total(selected, "点击量（全部）")
        base = {
            "Account": account_name, "Account Type": account_type,
            "Spend": spend if spend is not None else NA,
            "Impressions": impressions if impressions is not None else NA,
            "CTR": divide(clicks, impressions),
        }
        if account_type == "Performance":
            base.update({
                "Purchase": purchase if purchase is not None else NA,
                "Revenue": revenue if revenue is not None else NA,
                "ROAS": divide(revenue, spend), "CPA": divide(spend, purchase),
                "Reach": NA, "Frequency": NA,
            })
        else:
            base.update({
                "Purchase": NA, "Revenue": NA, "ROAS": NA, "CPA": NA,
                "Reach": reach if reach is not None else NA,
                "Frequency": divide(impressions, reach),
            })
        result.append(base)
    return result


def action_value(rows: Any, candidates: tuple[str, ...]) -> float | None:
    values = {str(row.get("action_type")): number(row.get("value")) for row in (rows or []) if row.get("action_type")}
    for candidate in candidates:
        if values.get(candidate) is not None:
            return values[candidate]
    return None


def fetch_meta_accounts(start: date, end: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from config import ACCOUNT_CONFIGS
    from meta_api import MetaMarketingAPI

    api = MetaMarketingAPI()
    results: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    for account in ACCOUNT_CONFIGS:
        try:
            payload = api._request(
                "GET", f"{api.base_url}/{account.api_id}/insights",
                params={
                    "fields": "spend,actions,action_values,purchase_roas,clicks,impressions,reach",
                    "time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
                    "access_token": api.access_token,
                },
            )
            rows = payload.get("data", [])
            if not rows:
                raise ValueError("Meta returned no account insight rows")
            row = rows[0]
            spend = number(row.get("spend")); impressions = number(row.get("impressions")); reach = number(row.get("reach")); clicks = number(row.get("clicks"))
            purchase = action_value(row.get("actions"), ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"))
            revenue = action_value(row.get("action_values"), ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"))
            native_roas = action_value(row.get("purchase_roas"), ("omni_purchase", "purchase", "offsite_conversion.fb_pixel_purchase"))
            base = {
                "Account": account.name, "Account Type": account.account_type.title(),
                "Spend": spend if spend is not None else NA,
                "Impressions": impressions if impressions is not None else NA,
                "CTR": divide(clicks, impressions),
            }
            if account.account_type == "brand":
                base.update({"Purchase": NA, "Revenue": NA, "ROAS": NA, "CPA": NA, "Reach": reach if reach is not None else NA, "Frequency": divide(impressions, reach)})
            else:
                base.update({"Purchase": purchase if purchase is not None else NA, "Revenue": revenue if revenue is not None else NA, "ROAS": native_roas if native_roas is not None else divide(revenue, spend), "CPA": divide(spend, purchase), "Reach": NA, "Frequency": NA})
            results.append(base)
        except Exception as exc:
            reviews.append({"Type": "Meta Account Fetch Error", "Account": account.name, "Value": type(exc).__name__, "Status": "Review"})
    return results, reviews


def fetch_creatives(start: date, end: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from config import ACCOUNT_CONFIGS
    from meta_api import MetaMarketingAPI

    api = MetaMarketingAPI()
    creatives: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    if not api.access_token:
        return creatives, [{"Type": "Input Error", "Value": "META_ACCESS_TOKEN unavailable; creative data not fetched", "Status": "Review"}]
    for account in ACCOUNT_CONFIGS:
        if account.account_id not in CREATIVE_ACCOUNT_IDS:
            continue
        try:
            payload = api._request(
                "GET", f"{api.base_url}/{account.api_id}/insights",
                params={
                    "fields": "campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,spend,actions,action_values,clicks,impressions,reach",
                    "level": "ad", "time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()}),
                    "limit": 500, "access_token": api.access_token,
                },
            )
            for row in payload.get("data", []):
                spend = number(row.get("spend"))
                if spend is None or spend <= 0:
                    continue
                creative = {"id": None, "name": None, "thumbnail_url": None, "image_hash": None, "video_id": None}
                status = None
                try:
                    detail = api._request("GET", f"{api.base_url}/{row.get('ad_id')}", params={"fields": "effective_status,creative{id,name,thumbnail_url,image_hash,video_id}", "access_token": api.access_token})
                    status = detail.get("effective_status")
                    creative.update(detail.get("creative") or {})
                except Exception as exc:
                    reviews.append({"Type": "Creative Detail Error", "Account": account.name, "Ad ID": row.get("ad_id"), "Value": type(exc).__name__, "Status": "Review"})
                creatives.append({
                    "Account": account.name, "Account Type": account.account_type, "Campaign ID": row.get("campaign_id"),
                    "Campaign": row.get("campaign_name"), "Ad Set ID": row.get("adset_id"), "Ad Set": row.get("adset_name"),
                    "Ad ID": row.get("ad_id"), "Ad": row.get("ad_name"), "Status": status or NA,
                    "Creative ID": creative.get("id") or NA, "Creative Name": creative.get("name") or NA,
                    "Thumbnail": creative.get("thumbnail_url") or NA, "Image Hash": creative.get("image_hash") or NA,
                    "Video ID": creative.get("video_id") or NA, "Spend": spend, "Clicks": number(row.get("clicks")) or 0,
                    "Impressions": number(row.get("impressions")) or 0, "Reach": number(row.get("reach")) or NA,
                    "Match Method": "Meta Ad creative object", "Match Confidence": "High" if creative.get("id") else "Low",
                    "Review Status": "Confirmed" if creative.get("id") else "Review",
                })
        except Exception as exc:
            reviews.append({"Type": "Meta Account Fetch Error", "Account": account.name, "Value": type(exc).__name__, "Status": "Review"})
    return sorted(creatives, key=lambda row: row["Spend"], reverse=True), reviews


def build_data(paths: WeeklyPaths, start: date, end: date, offline: bool = False) -> WeeklyData:
    bi = read_rows(paths.bi)
    google_perf = read_rows(paths.google_performance, header_row=3)
    google_conv = read_rows(paths.google_conversions, header_row=3)
    audience_rows = read_rows(paths.meta_audience)
    country_rows = read_rows(paths.meta_country)
    current = [bi_metrics(bi, start, end, channel) for channel in BI_OVERALL_CHANNELS]
    overview = current + [{
        "Period Start": start.isoformat(), "Period End": end.isoformat(), "Channel": "Paid Total",
        "Spend": sum(row["Spend"] for row in current if isinstance(row["Spend"], (int, float))),
        "Revenue": sum(row["Revenue"] for row in current if isinstance(row["Revenue"], (int, float))),
        "Orders": sum(row["Orders"] for row in current if isinstance(row["Orders"], (int, float))),
    }]
    paid = overview[-1]
    paid["ROI"] = divide(paid["Revenue"], paid["Spend"]); paid["CPA"] = divide(paid["Spend"], paid["Orders"]); paid["AOS"] = divide(paid["Revenue"], paid["Orders"]); paid["Payment CVR"] = NA
    weekly: list[dict[str, Any]] = []
    for offset in range(3, -1, -1):
        week_end = end - timedelta(days=offset * 7); week_start = week_end - timedelta(days=6)
        weekly.extend(bi_metrics(bi, week_start, week_end, channel) for channel in BI_OVERALL_CHANNELS)
    month_start = start.replace(day=1)
    month_to_date = [bi_metrics(bi, month_start, end, channel) for channel in BI_OVERALL_CHANNELS]
    google, unknown_actions, unmatched = google_metrics(google_perf, google_conv, start, end)
    audience, audience_reviews = meta_sample(audience_rows, start, end, True)
    country, _ = meta_sample(country_rows, start, end, False)
    meta_accounts = meta_account_metrics(audience)
    if offline:
        creative, creative_reviews = [], [{"Type": "Creative Input", "Value": "Offline mode: Meta creative API was not called", "Status": "Review"}]
        account_reviews = [{"Type": "Meta Account Input", "Value": "Offline mode: Brand account metrics unavailable in supplied samples", "Status": "Review"}]
    else:
        creative, creative_reviews = fetch_creatives(start, end)
        live_accounts, account_reviews = fetch_meta_accounts(start, end)
        if live_accounts:
            by_name = {row["Account"]: row for row in meta_accounts}
            by_name.update({row["Account"]: row for row in live_accounts})
            meta_accounts = [by_name[name] for name in META_ACCOUNT_TYPES]
    validation = [
        {"Check": "BI W27 rows", "Result": "PASS" if any(as_date(row.get("event_date(day)")) and start <= as_date(row.get("event_date(day)")) <= end for row in bi) else "FAIL"},
        {"Check": "Google period rows", "Result": "PASS" if google else "FAIL"},
        {"Check": "Meta audience W27", "Result": "PASS" if audience else "FAIL"},
        {"Check": "Meta country W27", "Result": "PASS" if country else "FAIL"},
        {"Check": "Meta creative coverage", "Result": "PASS" if creative else "REVIEW"},
    ]
    return WeeklyData(overview, weekly, month_to_date, google, meta_accounts, audience, country, creative, {
        "Input Validation": validation, "Unknown Google Conversions": unknown_actions,
        "Unmatched Google Campaigns": unmatched, "Unknown Meta Audiences": audience_reviews,
        "Creative Review": creative_reviews, "Meta Account Review": account_reviews,
    })


def write_table(workbook: Workbook, name: str, rows: list[dict[str, Any]]) -> None:
    sheet = workbook.create_sheet(name[:31])
    if not rows:
        sheet.append(["Status", "No data available"])
        return
    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)
    sheet.append(headers)
    for row in rows:
        sheet.append([row.get(header, NA) if row.get(header) is not None else NA for header in headers])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(horizontal="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 45)
        sheet.column_dimensions[column[0].column_letter].width = width


def save_reports(data: WeeklyData, output_dir: Path, start: date, end: date, week_label: str) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    weekly_path = output_dir / "Weekly_Report.xlsx"
    workbook = Workbook(); workbook.remove(workbook.active)
    notes = [{"Item": "Week Label", "Value": week_label}, {"Item": "Date Range", "Value": period_label(start, end)}, {"Item": "Generated At", "Value": datetime.now().astimezone().isoformat(timespec="seconds")}, {"Item": "Date Join", "Value": "Actual dates; platform week numbers ignored"}, {"Item": "Meta Funnel Denominator", "Value": "All Clicks"}, {"Item": "Missing Data", "Value": "N/A; never coerced to zero"}]
    for name, rows in (("Overview", data.overview), ("Week to Week", data.weekly), ("Month to Date", data.month_to_date), ("Channel Performance", data.overview), ("Google True Purchase", data.google), ("BI Comparison", data.overview), ("Meta Accounts", data.meta_accounts), ("Meta Audience", data.audience), ("Meta Country", data.country), ("Data Notes", notes)):
        write_table(workbook, name, rows)
    workbook.save(weekly_path)

    review_path = output_dir / "Review_Required.xlsx"
    review = Workbook(); review.remove(review.active)
    for name, rows in data.reviews.items():
        write_table(review, name, rows)
    review.save(review_path)

    creative_path = output_dir / "Creative_Report.html"
    body = [f"<h1>Meta Creative Report {html.escape(week_label)}</h1>", f"<p>{start.isoformat()} to {end.isoformat()} · all spending ads · generated {datetime.now().astimezone().isoformat(timespec='seconds')}</p>"]
    if not data.creative:
        body.append("<p><strong>Creative data unavailable. See Review_Required.xlsx.</strong></p>")
    else:
        body.append("<table><thead><tr>" + "".join(f"<th>{html.escape(key)}</th>" for key in data.creative[0]) + "</tr></thead><tbody>")
        for row in data.creative:
            cells = []
            for key, value in row.items():
                if key == "Thumbnail" and isinstance(value, str) and value.startswith("http"):
                    cells.append(f'<td><img src="{html.escape(value)}" alt="thumbnail" width="120"></td>')
                else:
                    cells.append(f"<td>{html.escape(str(value))}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        body.append("</tbody></table>")
    style = "body{font-family:Arial,sans-serif;margin:24px}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ddd;padding:6px;font-size:12px}th{background:#1f4e78;color:white;position:sticky;top:0}img{object-fit:cover}"
    creative_path.write_text(f"<!doctype html><html><head><meta charset='utf-8'><style>{style}</style></head><body>{''.join(body)}</body></html>", encoding="utf-8")
    return weekly_path, creative_path, review_path


def summary(data: WeeklyData, start: date, end: date, week_label: str) -> str:
    paid = next(row for row in data.overview if row["Channel"] == "Paid Total")
    review_count = sum(len(rows) for name, rows in data.reviews.items() if name != "Input Validation")
    return "\n".join([
        f"Weekly Ads Report {week_label}", "", f"Period: {start.isoformat()} to {end.isoformat()} (Sunday-Saturday)",
        f"Paid Spend: ${paid['Spend']:.2f}" if isinstance(paid["Spend"], (int, float)) else "Paid Spend: N/A",
        f"BI Revenue: ${paid['Revenue']:.2f}" if isinstance(paid["Revenue"], (int, float)) else "BI Revenue: N/A",
        f"BI ROI: {paid['ROI']:.2f}" if isinstance(paid["ROI"], (int, float)) else "BI ROI: N/A",
        f"Google campaigns: {len(data.google)} | Meta audience rows: {len(data.audience)} | Meta country rows: {len(data.country)} | Spending creatives: {len(data.creative)}",
        f"Review required: {review_count}", "", "Details: Weekly_Report.xlsx / Creative_Report.html / Review_Required.xlsx",
    ])


def run(args: argparse.Namespace) -> int:
    start = date.fromisoformat(args.since); end = date.fromisoformat(args.until)
    if end < start or (end - start).days != 6 or start.weekday() != 6 or end.weekday() != 5:
        raise ValueError("Weekly period must be exactly Sunday-Saturday")
    paths = discover_inputs(Path(args.input_dir))
    data = build_data(paths, start, end, args.offline)
    files = save_reports(data, Path(args.output_dir), start, end, args.week_label)
    message = summary(data, start, end, args.week_label)
    print(message)
    print("Generated:", *(str(path) for path in files), sep="\n- ")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Weekly Report V1 from Google, BI, and Meta data")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="outputs/weekly_report")
    parser.add_argument("--since", required=True)
    parser.add_argument("--until", required=True)
    parser.add_argument("--week-label", required=True)
    parser.add_argument("--offline", action="store_true", help="Do not call Meta API for creative data")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
