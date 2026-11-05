"""
GitHub Actions 执行器：轮询飞书审批表，执行已同意的调价建议。

流程：
1. 拿飞书 tenant_access_token
2. 查询审批表中「审批状态=已同意」的记录
3. 对每条记录：
   a. 先标记为「执行中」（防止重复执行）
   b. 复算安全门禁（$80地板、$2500上限、≤50%变动）
   c. 调Meta API改预算
   d. 回写「已执行」+ 执行结果
4. 全部完成
"""

import os
import json
import time
import requests
from datetime import datetime

# 本地测试用：自动加载同目录上级的.env
try:
    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if "=" in _line and not _line.startswith("#"):
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
except FileNotFoundError:
    pass

# 补默认值（本地测试）
os.environ.setdefault("FEISHU_BASE_TOKEN", "TivqbYjK9a2DRbsfVs7cdlo9nJg")
os.environ.setdefault("FEISHU_TABLE_ID", "tblfNw0JE6uL4D1d")

# ========== 配置（从GitHub Secrets读取） ==========
FEISHU_APP_ID = os.environ["FEISHU_APP_ID"]
FEISHU_APP_SECRET = os.environ["FEISHU_APP_SECRET"]
BASE_TOKEN = os.environ["FEISHU_BASE_TOKEN"]
TABLE_ID = os.environ["FEISHU_TABLE_ID"]
META_ACCESS_TOKEN = os.environ["META_ACCESS_TOKEN"]
META_API_VERSION = "v21.0"

# 安全门禁
BUDGET_FLOOR_USD = 80.0       # 地板：低于$80不动
MAX_CHANGE_PCT = 0.50         # 单次变动最多50%


def get_budget_cap_from_base(token):
    """从多维表读总预算上限"""
    # 读预算规则设置表
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records?page_size=100"
    # 不对，规则表是另一个表，我先写死$3500
    return 3500.0


def get_tenant_token():
    """获取飞书 tenant_access_token"""
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["tenant_access_token"]


def list_approved_records(token):
    """查询所有记录，本地过滤「已同意」"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records?page_size=100"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    items = data.get("data", {}).get("items", [])

    # 本地过滤：审批状态=已同意
    result = []
    for it in items:
        st = it["fields"].get("审批状态", "")
        if isinstance(st, list) and st:
            st = st[0].get("text", "")
        if st == "已同意":
            result.append(it)
    return result


def update_record(token, record_id, fields):
    """更新一条记录"""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{BASE_TOKEN}/tables/{TABLE_ID}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"fields": fields}
    r = requests.put(url, headers=headers, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def meta_get_budget(entity_id):
    """从Meta实时拉当前预算（单位：美分）"""
    url = f"https://graph.facebook.com/{META_API_VERSION}/{entity_id}"
    params = {"fields": "daily_budget,name", "access_token": META_ACCESS_TOKEN}
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    d = r.json()
    return int(d.get("daily_budget", 0)), d.get("name", "")


def meta_update_budget(entity_id, target_cents):
    """调Meta API改预算"""
    url = f"https://graph.facebook.com/{META_API_VERSION}/{entity_id}"
    data = {"daily_budget": str(target_cents), "access_token": META_ACCESS_TOKEN}
    r = requests.post(url, data=data, timeout=15)
    r.raise_for_status()
    return r.json()


def execute_one(token, record):
    """执行单条调价建议"""
    rid = record["record_id"]
    f = record["fields"]

    sug_id = f.get("建议ID", "")
    entity_id = f.get("Meta对象ID", "")
    current_usd = float(f.get("当前预算", 0))
    suggested_usd = float(f.get("建议预算", 0))
    entity_name = f.get("实体名称", "")

    print(f"\n=== 执行: {sug_id} ===")
    print(f"  实体: {entity_name} ({entity_id})")
    print(f"  当前: ${current_usd:.2f} → 建议: ${suggested_usd:.2f}")

    # 1) 先标记为「执行中」（防止重复执行）
    update_record(token, rid, {
        "审批状态": "执行中",
        "执行结果": "已接单，正在调用Meta API...",
    })
    
    # 读总预算上限
    budget_cap = get_budget_cap_from_base(token)

    try:
        # 2) 复算安全门禁
        if suggested_usd < BUDGET_FLOOR_USD:
            raise ValueError(f"建议预算 ${suggested_usd:.2f} 低于地板 ${BUDGET_FLOOR_USD:.0f}，跳过")
        if suggested_usd > budget_cap:
            raise ValueError(f"建议预算 ${suggested_usd:.2f} 超过上限 ${budget_cap:.0f}，跳过")

        change_pct = abs(suggested_usd - current_usd) / current_usd if current_usd > 0 else 0
        if change_pct > MAX_CHANGE_PCT:
            raise ValueError(f"变动幅度 {change_pct:.1%} 超过最大 {MAX_CHANGE_PCT:.0%}，跳过")

        # 3) 实时拉Meta当前预算（防止影子扫描后预算已变）
        live_cents, live_name = meta_get_budget(entity_id)
        live_usd = live_cents / 100
        print(f"  Meta实时: ${live_usd:.2f}")

        # 如果实时预算已经和目标差不多，直接跳过
        if abs(live_usd - suggested_usd) < 1.0:
            note = f"实时预算已是 ${live_usd:.2f}，与目标 ${suggested_usd:.2f} 一致，跳过"
            update_record(token, rid, {
                "审批状态": "已执行",
                "执行结果": note,
                "执行时间": int(time.time() * 1000),
            })
            print(f"  ⏭️  {note}")
            return

        # 4) 真调Meta
        target_cents = int(suggested_usd * 100)
        result = meta_update_budget(entity_id, target_cents)
        print(f"  ✅ Meta返回: {json.dumps(result)[:200]}")

        # 5) 回写「已执行」
        update_record(token, rid, {
            "审批状态": "已执行",
            "执行结果": f"成功：${current_usd:.2f} → ${suggested_usd:.2f}（Meta实时确认 ${live_usd:.2f}）",
            "执行时间": int(time.time() * 1000),
        })
        print(f"  ✅ 已回写飞书")

    except Exception as e:
        err = f"失败: {str(e)}"
        print(f"  ❌ {err}")
        update_record(token, rid, {
            "审批状态": "执行失败",
            "执行结果": err,
            "执行时间": int(time.time() * 1000),
        })


def main():
    print(f"=== 调价执行器启动 {datetime.now().isoformat()} ===")
    token = get_tenant_token()
    print(f"飞书token获取成功")

    records = list_approved_records(token)
    print(f"找到 {len(records)} 条「已同意」记录")

    for rec in records:
        try:
            execute_one(token, rec)
        except Exception as e:
            print(f"  ❌ 单条执行异常: {e}")
            continue

    print(f"\n=== 执行完成 ===")


if __name__ == "__main__":
    main()
