"""从飞书「调价审批」表读取已执行的调价历史，供冷却规则使用。

GitHub Actions 每次都是干净容器，本地 logs/budget_changes.jsonl 无法持久化，
因此审批表里的「已执行」记录才是冷却判断的唯一事实源。
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

BASE_DEFAULT = "TivqbYjK9a2DRbsfVs7cdlo9nJg"
TABLE_DEFAULT = "tblfNw0JE6uL4D1d"
CST = timezone(timedelta(hours=8))


def _tenant_token() -> str:
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def _cell_text(v: Any) -> str:
    if isinstance(v, list):
        return "".join(
            str(x.get("text") or x.get("name") or "") if isinstance(x, dict) else str(x)
            for x in v
        ).strip()
    if isinstance(v, dict):
        return str(v.get("text") or v.get("name") or "").strip()
    return str(v or "").strip()


def load_executed_history(keep_days: int = 10) -> list[dict[str, Any]]:
    """读取近 N 天已执行的调价记录，转成 rules.check_cooldown_limits 需要的格式"""
    base = os.environ.get("FEISHU_BASE_TOKEN", BASE_DEFAULT)
    table = os.environ.get("FEISHU_TABLE_ID", TABLE_DEFAULT)

    try:
        token = _tenant_token()
    except Exception as e:
        print(f"Warning: 冷却历史读取跳过（取token失败）: {e}")
        return []

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base}/tables/{table}/records"
    cutoff = (datetime.now(CST) - timedelta(days=keep_days)).timestamp() * 1000

    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params: dict[str, Any] = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        try:
            d = requests.get(url, headers=headers, params=params, timeout=20).json()
        except Exception as e:
            print(f"Warning: 冷却历史读取中断: {e}")
            break
        data = d.get("data", {}) or {}
        items.extend(data.get("items", []) or [])
        page_token = data.get("page_token", "") or ""
        if not data.get("has_more"):
            break

    history: list[dict[str, Any]] = []
    for it in items:
        f = it.get("fields", {}) or {}
        if _cell_text(f.get("审批状态")) != "已执行":
            continue
        ts = f.get("执行时间")
        if not isinstance(ts, (int, float)) or ts < cutoff:
            continue
        entity_id = _cell_text(f.get("Meta对象ID"))
        if not entity_id:
            continue
        try:
            pct = float(f.get("调整幅度%") or 0) / 100.0  # 表里存 20 表示 +20%
        except (TypeError, ValueError):
            continue
        if pct == 0:
            continue
        day = datetime.fromtimestamp(ts / 1000, CST).date().isoformat()
        history.append(
            {
                "entity_id": entity_id,
                "date": day,
                "adjustment_pct": pct,
                "action": f"{'INCREASE' if pct > 0 else 'DECREASE'}_{abs(round(pct * 100))}",
                "entity_name": _cell_text(f.get("实体名称")),
            }
        )
    return history
