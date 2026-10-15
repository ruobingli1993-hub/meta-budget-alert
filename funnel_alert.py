# -*- coding: utf-8 -*-
"""漏斗监控预警：逐小时对比 GA4 漏斗指标与上周同日同小时均值，
任一指标低于基准 70% 时发飞书预警。异常才发，正常静默。

用法:
  python funnel_alert.py              # 干跑：只打印判断结果
  python funnel_alert.py --send       # 异常时发飞书
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from ga4_api import GA4Error, hourly_event_counts
from feishu import FeishuWebhookClient

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

SESSION_EVENT = "session_start"
FUNNEL_EVENTS = {
    "session": SESSION_EVENT,
    "atc": "add_to_cart",
    "checkout": "begin_checkout",
    "cr": "purchase",
}

# 触发阈值：当前 < 上周同时段均值 × 0.7 即预警
ALERT_FACTOR = Decimal("0.7")
# 基准样本太小不触发（避免噪声）
MIN_BASELINE_SESSION = 10
MIN_BASELINE_COUNT = 3

ZERO = Decimal("0")


def fmt_pct(value: Decimal) -> str:
    return str((value * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) + "%"


def pct_or_na(value: Decimal | None) -> str:
    return "N/A" if value is None else fmt_pct(value)


def prev_week_hour(date_hour: str) -> str:
    dt = datetime.strptime(date_hour, "%Y%m%d%H") - timedelta(days=7)
    return dt.strftime("%Y%m%d%H")


def analyze(events_by_hour: dict[str, dict[str, int]]) -> dict:
    """输入 {dateHour: {metric: count}}，返回最近小时的分析结论。

    完整性守卫：GA4 小时数据存在 1-2 小时补齐延迟，最新 dateHour 可能只
    计入部分数据（特征：session 相对前一小时异常跳水且无更新数据）。若
    最新小时 session < 前一小时 × 50%，判定未补齐，回退到前一小时作为
    预警窗口。
    """
    if not events_by_hour:
        return {"error": "无任何小时数据"}
    ordered = sorted(events_by_hour.keys())
    candidate = ordered[-1]
    prev = ordered[-2] if len(ordered) >= 2 else None
    guard_used = False
    if prev:
        cand_session = events_by_hour[candidate].get("session", 0)
        prev_session = events_by_hour[prev].get("session", 0)
        # 前 1 小时必须连续且正常，候选异常跳水（<50%）→ 数据未补齐
        if prev_session >= 10 and cand_session < prev_session * 0.5:
            candidate = prev
            guard_used = True
    current_hour = candidate
    current = events_by_hour[current_hour]
    baseline_hour = prev_week_hour(current_hour)
    baseline = events_by_hour.get(baseline_hour, {})

    sessions = Decimal(current.get("session", 0))
    base_sessions = Decimal(baseline.get("session", 0))
    if sessions == 0:
        sessions = Decimal("1")  # 防除零，标记空窗口

    metrics = {}
    for key, event in FUNNEL_EVENTS.items():
        if key == "session":
            cur, base = sessions, base_sessions
        else:
            cur = Decimal(current.get(key, 0))
            base = Decimal(baseline.get(key, 0))
        cur_rate = cur / sessions if key != "session" else cur
        base_rate = (base / base_sessions) if (key != "session" and base_sessions > 0) else base
        ratio = None
        if base_sessions >= MIN_BASELINE_SESSION and base_rate > 0:
            ratio = cur_rate / base_rate
        metrics[key] = {
            "current": cur_rate,
            "baseline": base_rate,
            "ratio": ratio,
            "alert": ratio is not None and ratio < ALERT_FACTOR,
            "cur_count": cur,
            "base_count": base,
        }

    alerts = [k for k, m in metrics.items() if m["alert"]]
    return {
        "current_hour": current_hour,
        "baseline_hour": baseline_hour,
        "metrics": metrics,
        "alerts": alerts,
        "has_baseline": base_sessions >= MIN_BASELINE_SESSION,
        "guard_used": guard_used,
        "guard_note": f"最新小时 {ordered[-1]} 疑似数据未补齐，回退到 {current_hour}" if guard_used else "",
    }


def fetch_hourly(days: int = 9) -> dict[str, dict[str, int]]:
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    end = datetime.now().strftime("%Y-%m-%d")
    out: dict[str, dict[str, int]] = {}
    for key, event in FUNNEL_EVENTS.items():
        counts = hourly_event_counts(event, start, end)
        for date_hour, count in counts.items():
            out.setdefault(date_hour, {})[key] = count
    return out


def format_alert(result: dict) -> str:
    hour = result["current_hour"]
    dt = datetime.strptime(hour, "%Y%m%d%H")
    lines = [
        f"🚨 漏斗预警｜{dt.strftime('%m-%d %H:00')}（GA4 属性时区）",
        f"对比基准：{result['baseline_hour'][:8]} 同小时",
        "",
    ]
    labels = {"session": "会话", "atc": "加购率", "checkout": "结账率", "cr": "转化率"}
    for key, m in result["metrics"].items():
        flag = "❌" if m["alert"] else ("✅" if m["ratio"] is not None else "·")
        cur = m["current"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if key == "session" else fmt_pct(m["current"])
        base = m["baseline"].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if key == "session" else pct_or_na(m["baseline"])
        ratio_txt = f"（上周 {ALERT_FACTOR * 100}% 阈值）" if m["alert"] else ""
        lines.append(f"{flag} {labels[key]}：{cur} vs 上周 {base}{ratio_txt}")
    lines.append("")
    lines.append("建议：检查广告流量 / 落地页 / 支付环节，必要时收一收投放")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="GA4 漏斗小时预警")
    parser.add_argument("--send", action="store_true", help="异常时发送飞书（默认只打印）")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)

    try:
        by_hour = fetch_hourly()
    except GA4Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    result = analyze(by_hour)
    if "error" in result:
        print("NO_DATA:", result["error"])
        return 0

    print(f"窗口：{result['current_hour']} vs 上周 {result['baseline_hour']}（基准{'有效' if result['has_baseline'] else '样本不足'}）")
    for key, m in result["metrics"].items():
        print(f"  {key}: current={m['current']} baseline={m['baseline']} ratio={m['ratio']} alert={m['alert']}")

    if not result["alerts"]:
        print("OK: 无异常，不发送")
        return 0
    if not result["has_baseline"]:
        print("OK: 有异常信号但基准样本不足，不发送")
        return 0

    message = format_alert(result)
    print(message)
    if args.send:
        alert_webhook = os.getenv("FEISHU_ALERT_WEBHOOK_URL") or os.getenv("FEISHU_WEBHOOK_URL")
        if not alert_webhook:
            print("ERROR: FEISHU_ALERT_WEBHOOK_URL / FEISHU_WEBHOOK_URL empty", file=sys.stderr)
            return 1
        delivery = FeishuWebhookClient(webhook_url=alert_webhook).send_text(message)
        print(f"[Sent] http_status={delivery['http_status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
