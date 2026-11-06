# -*- coding: utf-8 -*-
"""
shadow_to_base.py — 影子建议 → 飞书多维表格「调价审批」写表脚本

数据源：outputs/adjustment_control_center_v1/current_shadow/latest.json
        （或命令行传入任意影子扫描 JSON）
目标表：「调价审批」Base（调价审批表）

审批分流：
  - INCREASE / DECREASE（有预算调整动作）→ 审批状态「待审批」，由人审
  - NO_CHANGE（不动预算）→ 审批状态「不调整」，留档供复盘，不需要人审批

幂等：按建议ID去重——已存在于表中的建议ID跳过，只写入新建议。
用法：
  python tools/shadow_to_base.py [--shadow PATH] [--dry-run]
  --shadow 影子扫描 JSON 路径（默认 current_shadow/latest.json）
  --dry-run 只打印将要写入的记录，不真正调用 lark-cli
"""
import argparse, json, pathlib, subprocess, sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_SHADOW = PROJECT_ROOT / "outputs" / "adjustment_control_center_v1" / "current_shadow" / "latest.json"

BASE_TOKEN = "TivqbYjK9a2DRbsfVs7cdlo9nJg"
TABLE_ID = "tblfNw0JE6uL4D1d"
LARK_CLI = "lark-cli"


def _fmt_money(v):
    if v is None:
        return "-"
    return f"{v:,.2f}"


def _fmt_roas(v):
    if v is None:
        return "-"
    return f"{v:.2f}"


def _fmt_pct(v):
    if v is None:
        return "-"
    return f"{v*100:.1f}%"


def human_reason(r):
    """把规则黑话翻译成人话：花费/购买/ROAS达标情况 + ATC/结账参考 + 健康/冷却状态 → 结论。"""
    d7 = r.get("last_7_completed_days") or {}
    d3 = r.get("last_3_completed_days") or {}
    d0 = r.get("last_completed_day") or {}
    target = r.get("target_roas")
    decision = r.get("decision")

    roas7, roas3, roas0 = d7.get("roas"), d3.get("roas"), d0.get("roas")
    hit7 = (roas7 is not None and target and roas7 >= target)
    parts = [f"近7天：花费${_fmt_money(d7.get('spend'))}、购买{int(d7.get('purchase') or 0)}单、ROAS {_fmt_roas(roas7)}（目标{target}，{'达标' if hit7 else '未达'}）"]
    atc, ck = d0.get("atc_rate"), d0.get("checkout_rate")
    if atc is not None or ck is not None:
        parts.append("昨：ATC率 " + _fmt_pct(atc) + "、结账率 " + _fmt_pct(ck))

    cooldown = r.get("cooldown", {}).get("status")
    reasons = (r.get("data_health") or {}).get("reasons") or []
    learning = r.get("learning_risk")

    if decision in ("INCREASE", "DECREASE"):
        if roas3 is not None and roas0 is not None and target:
            hit3 = roas3 >= target
            hit0 = roas0 >= target
            recent = f"近3天 ROAS {roas3:.2f}（{'达标' if hit3 else '未达'}）、昨 {roas0:.2f}（{'达标' if hit0 else '未达'}）"
            if decision == "INCREASE":
                why = "近期跑赢目标，建议加量放大"
            else:
                why = "近期跑输目标，建议收缩"
            state = f"{recent}，{why}，学习状态{learning or '正常'}"
        else:
            state = "数据健康，学习状态" + (learning or "正常")
        pct = r.get("budget_change_percent")
        verb = "加" if decision == "INCREASE" else "减"
        if pct is not None:
            concl = f"建议预算{verb}{pct:g}%（${_fmt_money(r.get('current_budget'))}→${_fmt_money(r.get('suggested_budget'))}）"
        else:
            concl = "建议调整预算（金额待确认）"
        parts.extend([f"状态：{state}", f"→ {concl}"])
    else:  # NO_CHANGE
        if cooldown == "ACTIVE":
            parts.append("状态：近24h已调整过预算（冷却期）")
            parts.append("→ 暂不调整，冷却过后再评估")
        elif reasons:
            human = "；".join(reasons)
            parts.append(f"状态：{human}")
            parts.append("→ 暂不调整（规则保护，不满足调整条件）")
        else:
            parts.append(f"状态：{_no_change_reason(roas3, roas0, target)}")
            parts.append("→ 暂不调整，下个扫描窗口再评估")
    return "；".join(parts)


def _no_change_reason(roas3, roas0, target):
    """解释 NO_CHANGE：核心是规则要求近3天和昨天同向达标/走弱才动，单日波动不动。"""
    if roas3 is None or roas0 is None or not target:
        return "关键 ROAS 数据不足，暂不调整"
    buf = target * 0.95
    h3, h0 = roas3 >= target, roas0 >= target
    if h3 and not h0:
        return f"近3天 ROAS {roas3:.2f} 达标，但昨 {roas0:.2f} 回落，等趋势确认再动"
    if not h3 and h0:
        return f"近3天 ROAS {roas3:.2f} 偏弱，但昨 {roas0:.2f} 已回到达标线，避免单日波动误判，先观察"
    if not h3 and not h0:
        return f"近3天 {roas3:.2f}、昨 {roas0:.2f} 均未达目标，应触发减预算（请检查门禁/冷却）"
    if roas3 >= buf:
        return f"近3天 ROAS {roas3:.2f} 在目标 {target} 的 95% 缓冲区内，保持观察"
    return "未同时满足加/减预算条件"


def approval_status_for(decision):
    if decision in ("INCREASE", "DECREASE"):
        return ["待审批"]
    return ["不调整"]


# 表内已有记录的读取：+record-list --format ndjson --output file
# 返回 {建议ID: {"record_id":..., "审批状态":..., "扫描日期":...}}
def fetch_existing_records(base_token, table_id, tmp_out):
    cmd = [LARK_CLI, "base", "+record-list", "--base-token", base_token,
           "--table-id", table_id, "--format", "ndjson",
           "--output", str(tmp_out), "--as", "user"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    existing = {}
    with open(tmp_out, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            rec = json.loads(line)
            sug = rec.get("建议ID")
            if not sug:
                continue
            st = rec.get("审批状态")
            st = st[0] if isinstance(st, list) and st else st
            existing[sug] = {
                "record_id": rec.get("record_id"),
                "审批状态": st,
                "扫描日期": rec.get("扫描日期"),
            }
    return existing


def _date_prefix(iso):
    """从 '2026-09-27T00:00:00+08:00' 取 '2026-09-27'；解析失败返回空串。"""
    if not iso:
        return ""
    return str(iso)[:10]

def build_records(shadow):
    records = []
    for r in shadow["records"]:
        snap = {
            "last_day": {k: r.get("last_completed_day", {}).get(k) for k in ("spend", "purchase", "purchase_value", "roas")},
            "last_3d": {k: r.get("last_3_completed_days", {}).get(k) for k in ("spend", "purchase", "purchase_value", "roas")},
            "last_7d": {k: r.get("last_7_completed_days", {}).get(k) for k in ("spend", "purchase", "purchase_value", "roas")},
            "learning_risk": r.get("learning_risk"),
            "generated_at": r.get("generated_at"),
        }
        records.append({
            "建议ID": r["suggestion_id"],
            "扫描日期": r["scan_date"],
            "规则版本": [r["rule_version"]],
            "账户": [r["account"]["name"]],
            "实体层级": [r["entity_type"]],
            "实体名称": r["entity_name"],
            "受众": [r["audience"]],
            "目标ROAS": r["target_roas"],
            "当前预算": r["current_budget"],
            "建议预算": r.get("suggested_budget"),
            "调整幅度%": r.get("budget_change_percent"),
            "决策": [r["decision"]],
            "决策理由": human_reason(r),
            "数据健康": [r["data_health"]["status"]],
            "冷却状态": [r["cooldown"]["status"]],
            "总预算检查": [r["total_budget_check"]["status"]],
            "审批状态": approval_status_for(r["decision"]),
            "Meta对象ID": str(r.get("entity_id") or ""),
            "预算层级": [r.get("budget_level")] if r.get("budget_level") else [],
            "广告账户ID": str((r.get("account") or {}).get("id") or ""),
            "数据快照": json.dumps(snap, ensure_ascii=False),
        })
    return records

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shadow", default=str(DEFAULT_SHADOW))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    shadow_path = pathlib.Path(args.shadow)
    if not shadow_path.exists():
        sys.exit(f"影子扫描文件不存在: {shadow_path}")
    shadow = json.loads(shadow_path.read_text(encoding="utf-8"))
    if "records" not in shadow:
        sys.exit("影子扫描 JSON 缺少 records 字段，请检查文件格式")

    tmp = PROJECT_ROOT / "_shadow_existing.ndjson"
    existing = fetch_existing_records(BASE_TOKEN, TABLE_ID, tmp)
    tmp.unlink(missing_ok=True)

    new_records = [r for r in build_records(shadow) if r["建议ID"] not in existing]

    # 过期分支：仍挂在「待审批」但扫描时间早于本轮的旧建议 → 自动标「已过期」
    # 不管是不是同一天，只要是更早的扫描，都过期，只留最新一轮
    new_scan_time = shadow["records"][0].get("scan_date") if shadow["records"] else ""
    expired = []
    if new_scan_time:
        for sug, info in existing.items():
            if info["审批状态"] == "待审批" and info["扫描日期"] and info["扫描日期"] < new_scan_time:
                expired.append((sug, info["record_id"]))

    if not new_records and not expired:
        print(f"无新建议、无过期：表内已有 {len(existing)} 条，本次 {len(shadow['records'])} 条全部已存在（建议ID 去重）")
        return

    if args.dry_run:
        if new_records:
            print(f"[dry-run] 将写入 {len(new_records)} 条新建议：")
            for r in new_records:
                print(f"  {r['建议ID']} | {r['账户'][0]} | {r['实体名称'][:40]} | {r['决策'][0]} | {r['当前预算']} -> {r['建议预算']}")
        if expired:
            print(f"[dry-run] 将过期 {len(expired)} 条待审批旧建议（早于 {new_scan_time}）：")
            for sug, rid in expired:
                print(f"  {rid} | {sug}")
        return

    # 1) 过期回写（先于写入新建议，保持看板干净）
    if expired:
        upd = {rid: {"审批状态": ["已过期"],
                     "执行结果": f"已过期：{new_scan_time} 新一轮扫描已覆盖，未执行（影子留档）"}
               for _, rid in expired}
        exp_file = PROJECT_ROOT / "_shadow_expire_payload.json"
        exp_file.write_text(json.dumps({"update_records": upd}, ensure_ascii=False), encoding="utf-8")
        r1 = subprocess.run([LARK_CLI, "base", "+record-batch-update", "--base-token", BASE_TOKEN,
                             "--table-id", TABLE_ID, "--json", f"@./{exp_file.name}", "--as", "user"],
                            capture_output=True, text=True, cwd=PROJECT_ROOT)
        if r1.returncode != 0:
            sys.exit(f"过期回写失败(code={r1.returncode}):\n{r1.stdout}\n{r1.stderr}")
        e1 = json.loads(r1.stdout)
        if not e1.get("ok"):
            sys.exit(f"过期回写失败: {json.dumps(e1.get('error', e1), ensure_ascii=False)}")
        print(f"已过期 {len(expired)} 条旧待审批建议")

    # 2) 写入新建议
    if not new_records:
        return
    payload = {"create_records": new_records}
    payload_file = PROJECT_ROOT / "_shadow_records_payload.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    cmd = [LARK_CLI, "base", "+record-batch-create", "--base-token", BASE_TOKEN,
           "--table-id", TABLE_ID, "--json", f"@./{payload_file.name}", "--as", "user"]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        sys.exit(f"lark-cli 调用失败(code={result.returncode}):\n{result.stdout}\n{result.stderr}")
    resp = json.loads(result.stdout)
    if not resp.get("ok"):
        sys.exit(f"写表失败: {json.dumps(resp.get('error', resp), ensure_ascii=False)}")
    ids = resp.get("data", {}).get("record_id_list", [])
    print(f"写入成功 {len(ids)} 条新建议（跳过 {len(existing)} 条已存在）：")
    for r in new_records:
        print(f"  {r['建议ID']} | {r['账户'][0]} | {r['实体名称'][:40]} | {r['决策'][0]}")

if __name__ == "__main__":
    main()
