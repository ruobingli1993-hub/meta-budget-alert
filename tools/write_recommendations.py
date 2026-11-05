"""
影子扫描结果写入飞书多维表格（替代webhook）。
只写有调价建议的记录（INCREASE/DECREASE），NO_CHANGE/DATA_ERROR不写。
"""
import os
import time
import requests
from datetime import datetime


# 账户ID到账户名称的映射（对应表里的"账户"select选项）
ACCOUNT_MAP = {
    "750289240467952": "QMDT—20240103",
    "5600626876733411": "销售三部—新主页账户",
    "1614799860253372": "Jelenew+",
    "4322234198077127": "Jelenew-New",
}


def get_tenant_token():
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def write_recommendations_to_bitable(recommendations, run_id):
    base_token = os.environ["FEISHU_BASE_TOKEN"]
    table_id = os.environ["FEISHU_TABLE_ID"]
    token = get_tenant_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    increase_actions = {"INCREASE_10", "INCREASE_15", "INCREASE_20", "INCREASE_25"}
    decrease_actions = {"DECREASE_10", "DECREASE_15", "DECREASE_20", "DECREASE_25"}
    all_actions = increase_actions | decrease_actions

    written = 0
    now_ms = int(time.time() * 1000)

    for rec in recommendations:
        action = getattr(rec, "proposed_action", "")
        if action not in all_actions:
            continue

        campaign_id = getattr(rec, "campaign_id", "") or ""
        adset_id = getattr(rec, "adset_id", "") or ""
        current_budget = getattr(rec, "current_budget", "0") or "0"
        new_budget = getattr(rec, "proposed_new_budget", "0") or "0"
        adj_pct = getattr(rec, "adjustment_percentage", "0") or "0"
        account_id = getattr(rec, "account_id", "") or ""
        entity_level = getattr(rec, "entity_level", "") or ""
        budget_model = getattr(rec, "budget_model", "") or ""
        cooldown = getattr(rec, "cooldown_status", "CLEAR") or "CLEAR"

        # 数据快照文本
        snap_parts = []
        roas_3d = getattr(rec, "last_3d_roas", None)
        roas_today = getattr(rec, "today_roas", None)
        if roas_3d:
            snap_parts.append(f"3天ROAS:{roas_3d}")
        if roas_today:
            snap_parts.append(f"今天ROAS:{roas_today}")
        atc = getattr(rec, "atc_rate", "")
        co = getattr(rec, "checkout_rate", "")
        if atc:
            snap_parts.append(f"ATC:{atc}")
        if co:
            snap_parts.append(f"Checkout:{co}")
        data_snapshot = " | ".join(snap_parts)

        fields = {
            "建议ID": f"SHD-{run_id[-8:]}-{campaign_id[-6:]}",
            "实体名称": getattr(rec, "campaign_name", ""),
            "Meta对象ID": campaign_id or adset_id,
            "当前预算": float(current_budget),
            "建议预算": float(new_budget),
            "审批状态": "待审批",
            "广告账户ID": account_id,
            "决策": action,
            "调整幅度%": float(adj_pct),
            "决策理由": getattr(rec, "reason", ""),
            "账户": ACCOUNT_MAP.get(account_id, account_id),
            "实体层级": entity_level,
            "预算层级": budget_model,
            "冷却状态": cooldown,
            "规则版本": "shadow-v0.2",
            "扫描日期": now_ms,
            "数据快照": data_snapshot,
            "总预算检查": "PASS",
        }

        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records"
        payload = {"fields": fields}
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200 and r.json().get("code") == 0:
            written += 1
        else:
            print(f"Write failed for {getattr(rec, 'campaign_name', 'unknown')}: {r.text[:300]}")

    return written
