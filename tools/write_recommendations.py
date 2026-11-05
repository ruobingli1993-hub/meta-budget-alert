"""
影子扫描结果写入飞书多维表格（替代webhook）。
只写有调价建议的记录（INCREASE/DECREASE），NO_CHANGE/DATA_ERROR不写。
"""
import os
import requests
from datetime import datetime


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

    written = 0
    for rec in recommendations:
        action = rec.get("proposed_action", "")
        if action not in {"INCREASE_10", "INCREASE_15", "INCREASE_20", "INCREASE_25",
                          "DECREASE_10", "DECREASE_15", "DECREASE_20", "DECREASE_25"}:
            continue

        fields = {
            "建议ID": f"SHD-{run_id[-8:]}-{rec.get('campaign_id', '')[-6:]}",
            "实体名称": rec.get("campaign_name", ""),
            "Meta对象ID": rec.get("campaign_id", "") or rec.get("adset_id", ""),
            "当前预算": float(rec.get("current_budget", 0) or 0),
            "建议预算": float(rec.get("proposed_new_budget", 0) or 0),
            "审批状态": "待审批",
            "广告账户ID": rec.get("account_id", ""),
            "决策": action,
            "调整幅度%": float(rec.get("adjustment_percentage", 0) or 0),
            "决策理由": rec.get("reason", ""),
        }

        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records"
        payload = {"fields": fields}
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200 and r.json().get("code") == 0:
            written += 1
        else:
            print(f"Write failed for {rec.get('campaign_name')}: {r.text[:200]}")

    return written
