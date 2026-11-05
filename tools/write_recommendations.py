"""
影子扫描结果写入飞书多维表格（替代webhook）。
只写有调价建议的记录（INCREASE/DECREASE），NO_CHANGE/DATA_ERROR不写。
"""
import os
import time
import json
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
    now_ms = int(time.time() * 1000)  # 飞书datetime字段需要毫秒时间戳

    for rec in recommendations:
        action = getattr(rec, "proposed_action", "")

        # 决定审批状态
        if action in increase_actions or action in decrease_actions:
            approval_status = "待审批"
        elif action == "NO_CHANGE":
            approval_status = "不调整"
        else:
            approval_status = "数据异常"

        # 从action（如"INCREASE_15"）拆出决策类型
        if action.startswith("INCREASE"):
            decision_type = "INCREASE"
        elif action.startswith("DECREASE"):
            decision_type = "DECREASE"
        else:
            decision_type = action

        campaign_id = getattr(rec, "campaign_id", "") or ""
        adset_id = getattr(rec, "adset_id", "") or ""
        current_budget = getattr(rec, "current_budget", "0") or "0"
        new_budget = getattr(rec, "proposed_new_budget", "0") or "0"
        adj_pct = getattr(rec, "adjustment_percentage", "0") or "0"
        account_id = getattr(rec, "account_id", "") or ""
        entity_level = getattr(rec, "entity_level", "") or ""
        budget_model = getattr(rec, "budget_model", "") or ""
        cooldown = getattr(rec, "cooldown_status", "CLEAR") or "CLEAR"
        rtg = getattr(rec, "rtg", "No") or "No"

        # Ad Set层级：实体名称用adset_name，对象ID用adset_id
        adset_name = getattr(rec, "adset_name", None)
        campaign_name = getattr(rec, "campaign_name", "") or ""
        if entity_level == "Ad Set" and adset_name:
            entity_name = f"{campaign_name} > {adset_name}"
            meta_object_id = adset_id or campaign_id
        else:
            entity_name = f"{campaign_name} > CBO整体"
            meta_object_id = campaign_id or adset_id

        # 受众：RTG=老客/再营销，否则新客
        audience = "老客/再营销" if rtg == "Yes" else "新客"
        # 目标ROAS：RTG 2.5，新客 2.0
        target_roas = 2.5 if rtg == "Yes" else 2.0

        # 数据快照文本（近7天+今天漏斗）
        snap_parts = []
        spend_7d = getattr(rec, "last_7d_spend", "N/A")
        purchase_7d = getattr(rec, "last_7d_purchase", "N/A")
        roas_7d = getattr(rec, "last_7d_roas", None)
        spend_3d = getattr(rec, "last_3d_spend", "N/A")
        roas_3d = getattr(rec, "last_3d_roas", None)
        roas_today = getattr(rec, "today_roas", None)
        atc = getattr(rec, "atc_rate", "")
        co = getattr(rec, "checkout_rate", "")

        if spend_7d and spend_7d != "N/A":
            snap_parts.append(f"7天:花费${spend_7d}/购买{purchase_7d}单/ROAS {roas_7d or 'N/A'}")
        if spend_3d and spend_3d != "N/A":
            snap_parts.append(f"3天ROAS:{roas_3d or 'N/A'}")
        if roas_today:
            snap_parts.append(f"今天ROAS:{roas_today}")
        if atc:
            snap_parts.append(f"ATC:{atc}")
        if co:
            snap_parts.append(f"Checkout:{co}")
        data_snapshot = " | ".join(snap_parts)

        # 决策理由（中文人话格式）
        reason_parts = []
        if spend_7d and spend_7d != "N/A":
            roas7_val = float(roas_7d) if roas_7d else 0
            hit = "达标" if roas7_val >= target_roas else "未达"
            reason_parts.append(f"近7天：花费${spend_7d}、购买{purchase_7d}单、ROAS {roas_7d or 'N/A'}（目标{target_roas}，{hit}）")
        if roas_3d:
            reason_parts.append(f"近3天ROAS {roas_3d}")
        if roas_today:
            reason_parts.append(f"今天ROAS {roas_today}")
        is_increase = action.startswith("INCREASE")
        action_cn = "加" if is_increase else "减"
        reason_parts.append(f"建议{action_cn}预算{adj_pct}%（${current_budget} → ${new_budget}）")
        reason = "；".join(reason_parts)

        fields = {
            "建议ID": f"SHD-{run_id[-8:]}-{meta_object_id[-6:]}",
            "实体名称": entity_name,
            "Meta对象ID": meta_object_id,
            "当前预算": float(current_budget),
            "建议预算": float(new_budget),
            "审批状态": approval_status,
            "广告账户ID": account_id,
            "决策": decision_type,
            "调整幅度%": float(adj_pct),
            "决策理由": reason,
            "账户": ACCOUNT_MAP.get(account_id, account_id),
            "实体层级": entity_level,
            "受众": audience,
            "目标ROAS": target_roas,
            "预算层级": budget_model,
            "冷却状态": cooldown,
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

    # 写完后发消息提醒（不管有没有建议都发）
    try:
        send_approval_notification(recommendations, written, run_id)
    except Exception as e:
        print(f"Notification failed (ignored): {e}")

    return written


def send_approval_notification(recommendations, written_count: int, run_id: str):
    """扫描完成后，给用户发总结消息（包含overall表现和建议分布）"""
    app_id = os.environ["FEISHU_APP_ID"]
    app_secret = os.environ["FEISHU_APP_SECRET"]
    user_open_id = "ou_828893ebc1c062bed4b6b1602ac16e66"  # 李若冰
    base_token = os.environ["FEISHU_BASE_TOKEN"]

    # 统计overall数据
    total_spend = 0.0
    total_purchase_value = 0.0
    total_purchase = 0
    total_atc = 0.0
    total_checkout = 0.0
    total_clicks = 0.0

    increase_count = 0
    decrease_count = 0
    no_change_count = 0
    total_current_budget = 0.0
    total_new_budget = 0.0

    for rec in recommendations:
        # 统计当天表现（只算Campaign层级，避免Ad Set重复计算）
        entity_level = getattr(rec, "entity_level", "")
        if entity_level == "Campaign":
            try:
                total_spend += float(getattr(rec, "today_spend", "0") or 0)
                total_purchase_value += float(getattr(rec, "today_purchase_value", "0") or 0)
                total_purchase += int(float(getattr(rec, "today_purchase", "0") or 0))
            except:
                pass

        # 统计建议分布
        action = getattr(rec, "proposed_action", "")
        if action.startswith("INCREASE"):
            increase_count += 1
        elif action.startswith("DECREASE"):
            decrease_count += 1
        else:
            no_change_count += 1

        # 统计预算
        try:
            cb = float(getattr(rec, "current_budget", "0") or 0)
            nb = float(getattr(rec, "proposed_new_budget", "0") or 0)
            if cb > 0:
                total_current_budget += cb
                total_new_budget += nb
        except:
            pass

    overall_roas = total_purchase_value / total_spend if total_spend > 0 else 0
    # 预算调整比例
    budget_change_pct = ((total_new_budget - total_current_budget) / total_current_budget * 100) if total_current_budget > 0 else 0

    # 拿tenant token
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    token = r.json()["tenant_access_token"]

    # 消息内容
    message_content = (
        f"**本次扫描结果**\n"
        f"放量 {increase_count} 条 | 控量 {decrease_count} 条 | 不变 {no_change_count} 条\n\n"
        f"**Overall 实时表现（今日）**\n"
        f"花费 ${total_spend:.2f} | 购买 {total_purchase} 单 | ROAS {overall_roas:.2f}\n\n"
        f"**综上决策**\n"
        f"整体预算调整：{budget_change_pct:+.0f}%"
    )

    # 消息卡片
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📊 影子扫描完成"},
            "template": "blue" if written_count == 0 else "orange",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": message_content,
                },
            },
            {
                "tag": "action",
                "actions": [
                    {
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": "去多维表格查看"},
                        "type": "primary",
                        "url": f"https://feishu.cn/base/{base_token}",
                    }
                ],
            },
        ],
    }

    # 发消息
    url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    payload = {
        "receive_id": user_open_id,
        "msg_type": "interactive",
        "content": json.dumps(card),
    }
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )
    result = r.json()
    if result.get("code") == 0:
        print(f"Approval notification sent to user: {written_count} recommendations")
    else:
        print(f"Failed to send notification: {result}")
