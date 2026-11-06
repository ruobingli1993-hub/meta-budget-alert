from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SKILL_DIR / "config.json"

NO_WRITE_ACTIONS = {"NO_CHANGE", "DATA_INSUFFICIENT", "DATA_ERROR", "MANUAL_REVIEW", "COOLDOWN"}
DECREASE_ACTIONS = {
    "DECREASE_25": Decimal("-0.25"),
    "DECREASE_20": Decimal("-0.20"),
    "DECREASE_15": Decimal("-0.15"),
    "DECREASE_10": Decimal("-0.10"),
}
INCREASE_ACTIONS = {
    "INCREASE_25": Decimal("0.25"),
    "INCREASE_20": Decimal("0.20"),
    "INCREASE_15": Decimal("0.15"),
    "INCREASE_10": Decimal("0.10"),
}


@dataclass(frozen=True)
class MetricWindow:
    spend: Decimal
    purchase: Decimal
    purchase_value: Decimal
    atc: Decimal
    checkout: Decimal
    clicks: Decimal
    impressions: Decimal

    @property
    def roas(self) -> Decimal | None:
        if self.spend == 0 or self.purchase_value == 0:
            return None
        return self.purchase_value / self.spend

    @property
    def atc_rate(self) -> Decimal | None:
        return self.atc / self.clicks if self.clicks else None

    @property
    def checkout_rate(self) -> Decimal | None:
        return self.checkout / self.clicks if self.clicks else None

    @property
    def purchase_rate(self) -> Decimal | None:
        return self.purchase / self.clicks if self.clicks else None


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def date_ranges(today: date | None = None) -> dict[str, dict[str, str]]:
    current = today or datetime.now().date()
    yesterday = current - timedelta(days=1)
    three_days_ago = current - timedelta(days=3)
    thirty_days_ago = current - timedelta(days=30)
    return {
        "last_3_complete_days": {"since": three_days_ago.isoformat(), "until": yesterday.isoformat()},
        "today": {"since": current.isoformat(), "until": current.isoformat()},
        "last_30_complete_days": {"since": thirty_days_ago.isoformat(), "until": yesterday.isoformat()},
    }


def determine_account_mode(total_roas: Decimal | None, config: dict[str, Any]) -> str:
    """判断总账户模式：aggressive / normal / conservative"""
    if total_roas is None:
        return "normal"
    weighted_target = Decimal(str(config["weighted_target_roas"]))
    aggressive_threshold = weighted_target * Decimal(str(config["auto_mode_thresholds"]["aggressive_above_weighted_pct"]))
    conservative_threshold = weighted_target * Decimal(str(config["auto_mode_thresholds"]["conservative_below_weighted_pct"]))
    if total_roas >= aggressive_threshold:
        return "aggressive"
    if total_roas <= conservative_threshold:
        return "conservative"
    return "normal"


def determine_entity_regime(roas_3d: Decimal | None, target_roas: Decimal, config: dict[str, Any]) -> tuple[str, str]:
    """判断实体状态：BULL / HEALTHY / NEUTRAL / BEAR / SEVERE_BEAR，按目标比例算"""
    if roas_3d is None:
        return "DATA_INSUFFICIENT", "3天ROAS不可用"
    
    bull_threshold = target_roas * Decimal(str(config["regime_thresholds"]["bull_above_target_pct"]))
    healthy_threshold = target_roas * Decimal(str(config["regime_thresholds"]["healthy_above_target_pct"]))
    neutral_threshold = target_roas * Decimal(str(config["regime_thresholds"]["neutral_above_target_pct"]))
    bear_threshold = target_roas * Decimal(str(config["regime_thresholds"]["bear_above_target_pct"]))
    
    if roas_3d >= bull_threshold:
        return "BULL", f"3天ROAS {roas_3d:.2f} ≥ 目标{target_roas:.2f}×1.2"
    if roas_3d >= healthy_threshold:
        return "HEALTHY", f"3天ROAS {roas_3d:.2f} ≥ 目标{target_roas:.2f}"
    if roas_3d >= neutral_threshold:
        return "NEUTRAL", f"3天ROAS {roas_3d:.2f} ≥ 目标{target_roas:.2f}×0.8"
    if roas_3d >= bear_threshold:
        return "BEAR", f"3天ROAS {roas_3d:.2f} ≥ 目标{target_roas:.2f}×0.6"
    return "SEVERE_BEAR", f"3天ROAS {roas_3d:.2f} < 目标{target_roas:.2f}×0.6"


def determine_scene(today_roas: Decimal | None, roas_3d: Decimal | None, target_roas: Decimal) -> tuple[str, str]:
    """判断是哪个场景（8种场景）"""
    if today_roas is None or roas_3d is None:
        return "scene_unknown", "ROAS不可用"
    
    today_pass = today_roas >= target_roas
    today_neutral = (today_roas >= target_roas * Decimal("0.8")) and (today_roas < target_roas)
    today_below = today_roas < target_roas * Decimal("0.8")
    
    roas_3d_pass = roas_3d >= target_roas
    roas_3d_neutral = (roas_3d >= target_roas * Decimal("0.8")) and (roas_3d < target_roas)
    roas_3d_below = roas_3d < target_roas * Decimal("0.8")
    
    if today_pass and roas_3d_pass:
        return "scene_1_today_pass_3d_pass", "当天达标且3天达标"
    if today_pass and roas_3d_neutral:
        return "scene_2_today_pass_3d_neutral", "当天达标但3天一般"
    if today_pass and roas_3d_below:
        return "scene_3_today_pass_3d_below", "当天达标但3天较差"
    if today_neutral and roas_3d_pass:
        return "scene_4_today_neutral_3d_pass", "当天一般但3天达标"
    if today_below and roas_3d_pass:
        return "scene_5_today_below_3d_pass", "当天较差但3天达标"
    if today_neutral and roas_3d_neutral:
        return "scene_6_today_neutral_3d_neutral", "当天和3天都一般"
    if today_below and roas_3d_neutral:
        return "scene_7_today_below_3d_neutral", "当天较差但3天一般"
    if today_below and roas_3d_below:
        return "scene_8_today_below_3d_below", "当天和3天都较差"
    
    return "scene_unknown", "未知场景"


def has_last_3d_sample(metrics: MetricWindow, config: dict[str, Any]) -> bool:
    sample = config["sample_protection"]
    return metrics.spend >= Decimal(str(sample["last_3d_spend_min"]))


def has_today_sample(metrics: MetricWindow, config: dict[str, Any]) -> bool:
    # 数据保护只看3天花费，当天不限制
    return True


def determine_account_regime(last_3d: MetricWindow, today: MetricWindow, funnel_anomaly: bool, config: dict[str, Any]) -> tuple[str, str]:
    if not has_last_3d_sample(last_3d, config):
        return "DATA_INSUFFICIENT", "Last 3 complete days sample is insufficient."

    last_3d_roas = last_3d.roas
    today_roas = today.roas
    if last_3d_roas is None:
        return "DATA_INSUFFICIENT", "Last 3 complete days ROAS is unavailable; account regime cannot be classified."

    if not has_today_sample(today, config):
        return "NEUTRAL", "Today sample is insufficient; account direction needs observation."

    if today_roas is None:
        return "DATA_ERROR", "Today purchase value or ROAS is unavailable."

    if last_3d_roas >= Decimal("4.0") and today_roas >= Decimal("3.0") and last_3d.purchase >= Decimal("3") and not funnel_anomaly:
        return "BULL", "Account 3D and today ROAS are both clearly above target."
    if last_3d_roas >= Decimal("3.0"):
        return "HEALTHY", "Last 3 complete days ROAS reached target."
    if last_3d_roas >= Decimal("2.5"):
        return "NEUTRAL", "Last 3 complete days ROAS is neutral."
    if last_3d_roas < Decimal("2.0") and today_roas < Decimal("2.0"):
        return "SEVERE_BEAR", "Last 3 complete days and today ROAS are both below 2.0."
    return "BEAR", "Last 3 complete days ROAS is below 2.5."


def detect_funnel_anomaly(current: MetricWindow, avg_30d: MetricWindow, config: dict[str, Any]) -> tuple[bool, str]:
    target = Decimal(str(config["target_purchase_roas"]))
    atc_strong = avg_30d.atc_rate is not None and current.atc_rate is not None and avg_30d.atc_rate > 0 and current.atc_rate > avg_30d.atc_rate * Decimal("1.2")
    checkout_strong = avg_30d.checkout_rate is not None and current.checkout_rate is not None and avg_30d.checkout_rate > 0 and current.checkout_rate > avg_30d.checkout_rate * Decimal("1.2")
    purchase_not_growing = avg_30d.purchase_rate is not None and current.purchase_rate is not None and avg_30d.purchase_rate > 0 and current.purchase_rate <= avg_30d.purchase_rate
    roas_low = current.roas is None or current.roas < target
    if (atc_strong or checkout_strong) and (purchase_not_growing or roas_low):
        return True, "Front-end funnel events improved, but purchase did not grow with them."
    return False, ""


def is_rtg(name: str, config: dict[str, Any]) -> bool:
    lowered = name.lower()
    return any(keyword.lower() in lowered for keyword in config["rtg_keywords"])


def pct_from_action(action: str) -> Decimal:
    if action in INCREASE_ACTIONS:
        return INCREASE_ACTIONS[action]
    if action in DECREASE_ACTIONS:
        return DECREASE_ACTIONS[action]
    return Decimal("0")


def adjust_action_by_mode(action: str, mode: str) -> str:
    """根据模式调整动作档位
    aggressive: 放量大一档，缩量小一档
    conservative: 放量小一档，缩量大一档
    """
    if mode == "normal" or action not in INCREASE_ACTIONS and action not in DECREASE_ACTIONS:
        return action
    
    increase_order = ["INCREASE_10", "INCREASE_15", "INCREASE_20", "INCREASE_25"]
    decrease_order = ["DECREASE_10", "DECREASE_15", "DECREASE_20", "DECREASE_25"]
    
    if action in increase_order:
        idx = increase_order.index(action)
        if mode == "aggressive" and idx < len(increase_order) - 1:
            return increase_order[idx + 1]  # 往大调一档
        elif mode == "conservative" and idx > 0:
            return increase_order[idx - 1]  # 往小调一档
    elif action in decrease_order:
        idx = decrease_order.index(action)
        if mode == "aggressive" and idx > 0:
            return decrease_order[idx - 1]  # 往小调一档（缩量更小）
        elif mode == "conservative" and idx < len(decrease_order) - 1:
            return decrease_order[idx + 1]  # 往大调一档（缩量更大）
    
    return action


def proposed_budget(current_budget: Decimal | None, action: str, config: dict[str, Any]) -> Decimal | None:
    if current_budget is None or action in NO_WRITE_ACTIONS:
        return None
    pct = pct_from_action(action)
    if pct == 0:
        return None
    new_budget = current_budget * (Decimal("1") + pct)
    floor = Decimal(str(config["budget_floor_usd"]))
    if new_budget < floor:
        new_budget = floor
    return new_budget.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def learning_limited_action(action: str, current_budget: Decimal | None = None) -> str:
    # 预算超过$200就不限制学习期了
    if current_budget is not None and current_budget >= Decimal("200"):
        return action
    if action in {"INCREASE_25", "INCREASE_20", "INCREASE_15"}:
        return "INCREASE_10"
    if action in {"DECREASE_25", "DECREASE_20", "DECREASE_15"}:
        return "DECREASE_10"
    return action


def load_change_history(config: dict[str, Any]) -> list[dict[str, Any]]:
    """加载历史调整记录"""
    change_log_path = SKILL_DIR.parent.parent / config.get("change_log_path", "logs/budget_changes.jsonl")
    if not change_log_path.exists():
        return []
    records = []
    for line in change_log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def get_entity_today_changes(entity_id: str, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """获取某个实体今天的调整记录"""
    today_str = date.today().isoformat()
    return [r for r in history if r.get("entity_id") == entity_id and r.get("date") == today_str]


def get_entity_recent_changes(entity_id: str, history: list[dict[str, Any]], days: int = 7) -> list[dict[str, Any]]:
    """获取某个实体最近几天的调整记录"""
    cutoff = date.today() - timedelta(days=days)
    result = []
    for r in history:
        if r.get("entity_id") != entity_id:
            continue
        try:
            r_date = date.fromisoformat(r.get("date", ""))
            if r_date >= cutoff:
                result.append(r)
        except (ValueError, TypeError):
            continue
    return result


def check_cooldown_limits(
    entity_id: str,
    action: str,
    current_budget: Decimal | None,
    config: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> tuple[str, str]:
    """检查冷却时间限制，返回(最终动作, 原因)"""
    if action in NO_WRITE_ACTIONS:
        return action, ""
    
    cooldown_config = config.get("cooldown", {})
    if history is None:
        history = load_change_history(config)
    
    # 1. 单日最多调2次
    max_per_day = cooldown_config.get("max_adjustments_per_day", 2)
    today_changes = get_entity_today_changes(entity_id, history)
    if len(today_changes) >= max_per_day:
        return "COOLDOWN", f"今天已经调过{len(today_changes)}次了，达到上限{max_per_day}次"
    
    # 2. 一天累计±30%
    max_daily_change = cooldown_config.get("max_daily_change_pct", 0.3)
    today_pct_sum = sum(Decimal(str(r.get("adjustment_pct", 0))) for r in today_changes)
    new_pct = pct_from_action(action)
    total_pct = today_pct_sum + new_pct
    if abs(total_pct) > Decimal(str(max_daily_change)):
        return "COOLDOWN", f"今天累计调整{abs(total_pct)*100:.1f}%，超过单日上限{max_daily_change*100:.0f}%"
    
    # 3. 连续同方向调整3天后冷却2天
    max_same_direction = cooldown_config.get("max_same_direction_days", 3)
    cooldown_days = cooldown_config.get("cooldown_days_after_streak", 2)
    recent_changes = get_entity_recent_changes(entity_id, history, days=max_same_direction + cooldown_days)
    
    # 按天分组，计算每天的净调整幅度
    from collections import defaultdict
    daily_net = defaultdict(Decimal)
    for r in recent_changes:
        r_date = r.get("date", "")
        try:
            pct = Decimal(str(r.get("adjustment_pct", 0)))
            daily_net[r_date] += pct
        except (ValueError, TypeError):
            continue
    
    # 按日期排序
    sorted_dates = sorted(daily_net.keys())
    
    # 判断连续同方向天数（按净幅度）
    is_increase = action in INCREASE_ACTIONS
    current_streak = 0
    in_cooldown = False
    cooldown_remaining = 0
    
    # 从最近的天往前数
    for d in reversed(sorted_dates):
        net = daily_net[d]
        if (is_increase and net > 0) or (not is_increase and net < 0):
            current_streak += 1
        else:
            break
    
    # 检查是否在冷却期
    if current_streak >= max_same_direction:
        # 看最后一次调整是哪天
        if sorted_dates:
            last_change_date = date.fromisoformat(sorted_dates[-1])
            days_since_last = (date.today() - last_change_date).days
            if days_since_last < cooldown_days:
                cooldown_remaining = cooldown_days - days_since_last
                in_cooldown = True
    
    if in_cooldown:
        return "COOLDOWN", f"连续{current_streak}天同方向调整（按天净幅度），冷却中，还剩{cooldown_remaining}天"
    
    return action, ""


def record_change(entity_id: str, entity_name: str, action: str, old_budget: Decimal | None, new_budget: Decimal | None, config: dict[str, Any]) -> None:
    """记录一次调整"""
    change_log_path = SKILL_DIR.parent.parent / config.get("change_log_path", "logs/budget_changes.jsonl")
    change_log_path.parent.mkdir(parents=True, exist_ok=True)
    
    pct = pct_from_action(action)
    direction = "increase" if action in INCREASE_ACTIONS else "decrease"
    
    record = {
        "date": date.today().isoformat(),
        "entity_id": entity_id,
        "entity_name": entity_name,
        "action": action,
        "direction": direction,
        "adjustment_pct": str(pct),
        "old_budget": str(old_budget) if old_budget else None,
        "new_budget": str(new_budget) if new_budget else None,
    }
    
    with change_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def is_brand(name: str, config: dict[str, Any]) -> bool:
    lowered = name.lower()
    return any(keyword.lower() in lowered for keyword in config.get("brand_keywords", []))


def evaluate_entity(
    entity_id: str,
    entity_name: str,
    entity_level: str,
    budget_model: str,
    rtg: bool,
    account_mode: str,
    last_3d: MetricWindow,
    today: MetricWindow,
    avg_7d: MetricWindow | None,
    current_budget: Decimal | None,
    learning_status: str,
    config: dict[str, Any],
    rtg_budget_ratio: float = 0,
) -> dict[str, Any]:
    reason_parts = []
    
    # Brand账户直接NO_CHANGE
    if is_brand(entity_name, config):
        reason = build_decision_reason(today, last_3d, avg_7d, Decimal("0"), "brand", "BRAND", account_mode, "NO_CHANGE", "NO_CHANGE", ["Brand账户不参与自动调价"])
        return {
            "proposed_action": "NO_CHANGE",
            "proposed_new_budget": current_budget,
            "adjustment_percentage": 0,
            "reason": reason,
            "funnel_anomaly": False,
            "optimization_hint": "",
        }
    
    # 数据不够检查
    if not has_last_3d_sample(last_3d, config):
        reason = build_decision_reason(today, last_3d, avg_7d, Decimal("0"), "data_insufficient", "DATA_INSUFFICIENT", account_mode, "NO_CHANGE", "NO_CHANGE", ["3天花费不足$240，样本不够"])
        return {
            "proposed_action": "DATA_INSUFFICIENT",
            "proposed_new_budget": current_budget,
            "adjustment_percentage": 0,
            "reason": reason,
            "funnel_anomaly": False,
            "optimization_hint": "",
        }
    
    if last_3d.roas is None or today.roas is None:
        reason = build_decision_reason(today, last_3d, avg_7d, Decimal("0"), "data_error", "DATA_ERROR", account_mode, "NO_CHANGE", "NO_CHANGE", ["ROAS不可用"])
        return {
            "proposed_action": "DATA_ERROR",
            "proposed_new_budget": current_budget,
            "adjustment_percentage": 0,
            "reason": reason,
            "funnel_anomaly": False,
            "optimization_hint": "",
        }
    
    # 确定目标ROAS（新客2.0，老客2.5）
    target_roas = Decimal(str(config["target_roas_rtg"])) if rtg else Decimal(str(config["target_roas_non_rtg"]))
    
    # 判断实体状态
    entity_regime, regime_reason = determine_entity_regime(last_3d.roas, target_roas, config)
    if entity_regime in {"DATA_INSUFFICIENT", "DATA_ERROR"}:
        reason = build_decision_reason(today, last_3d, avg_7d, target_roas, "regime_error", entity_regime, account_mode, "NO_CHANGE", "NO_CHANGE", [regime_reason])
        return {
            "proposed_action": entity_regime,
            "proposed_new_budget": current_budget,
            "adjustment_percentage": 0,
            "reason": reason,
            "funnel_anomaly": False,
            "optimization_hint": "",
        }
    
    # 判断场景
    scene, scene_reason = determine_scene(today.roas, last_3d.roas, target_roas)
    reason_parts.append(scene_reason)
    reason_parts.append(regime_reason)
    
    # 查动作表
    base_action = "NO_CHANGE"
    
    scene_actions = config["scene_actions"].get(scene, {})
    if scene == "scene_1_today_pass_3d_pass":
        # 场景1：当天达标且3天达标，按实体状态和账户模式查
        regime_actions = scene_actions.get(entity_regime, {})
        if isinstance(regime_actions, dict):
            base_action = regime_actions.get(account_mode, "NO_CHANGE")
        else:
            base_action = regime_actions
    elif scene == "scene_4_today_neutral_3d_pass":
        # 场景4：当天一般但3天达标，按账户模式查
        base_action = scene_actions.get(account_mode, "NO_CHANGE")
    elif scene == "scene_5_today_below_3d_pass":
        # 场景5：当天较差但3天达标，按账户模式查
        base_action = scene_actions.get(account_mode, "NO_CHANGE")
    elif scene == "scene_8_today_below_3d_below":
        # 场景8：当天和3天都较差，按实体状态查
        base_action = scene_actions.get(entity_regime, "NO_CHANGE")
    else:
        # 其他场景直接用default
        base_action = scene_actions.get("default", "NO_CHANGE")
    
    action = base_action
    
    # 学习期限制
    if learning_status.lower() in {"learning", "learning limited", "learning_limited"}:
        original = action
        action = learning_limited_action(action, current_budget)
        if original != action:
            reason_parts.append(f"学习期限制：动作从{original}调整为{action}（预算<$200）")
        elif action != "NO_CHANGE":
            reason_parts.append("学习期仅允许小幅调整")
    
    # 老客预算占比限制（加预算时检查）
    max_rtg_ratio = config.get("max_rtg_budget_ratio", 0.3)
    if rtg and action in INCREASE_ACTIONS and rtg_budget_ratio > max_rtg_ratio:
        action = "NO_CHANGE"
        reason_parts.append(f"老客预算占比已达{rtg_budget_ratio:.1%}，超过{max_rtg_ratio:.0%}上限，不再加预算")
    
    # 冷却时间检查
    if action not in NO_WRITE_ACTIONS:
        action, cooldown_reason = check_cooldown_limits(
            entity_id=entity_id,
            action=action,
            current_budget=current_budget,
            config=config,
        )
        if cooldown_reason:
            reason_parts.append(cooldown_reason)
    
    # 生成详细理由
    reason = build_decision_reason(today, last_3d, avg_7d, target_roas, scene, entity_regime, account_mode, base_action, action, reason_parts)
    
    # 最后加上预算信息
    final_pct = pct_from_action(action)
    proposed_budget = None
    if current_budget and action not in NO_WRITE_ACTIONS:
        proposed_budget = current_budget * (1 + final_pct)
    
    budget_cap = config.get("total_budget_cap", 3500)
    budget_info = f"【预算】当前${current_budget or 0:.0f} → 建议${proposed_budget or current_budget or 0:.0f}（{final_pct*100:+.0f}%）；总预算cap ${budget_cap}"
    
    reason = reason + "；" + budget_info
    
    # 构建返回字典
    proposed_new_budget = None
    adjustment_percentage = 0
    if current_budget and action not in NO_WRITE_ACTIONS:
        proposed_new_budget = current_budget * (1 + final_pct)
        adjustment_percentage = float(final_pct * 100)
    
    return {
        "proposed_action": action,
        "proposed_new_budget": proposed_new_budget,
        "adjustment_percentage": adjustment_percentage,
        "reason": reason,
        "funnel_anomaly": False,
        "optimization_hint": "",
    }


def build_decision_reason(
    today: MetricWindow,
    last_3d: MetricWindow,
    avg_7d: MetricWindow | None,
    target_roas: Decimal,
    scene: str,
    entity_regime: str,
    account_mode: str,
    base_action: str,
    final_action: str,
    reason_parts: list[str],
) -> str:
    """构建详细的决策理由"""
    parts = []
    
    # 1. 当日数据
    today_roas_str = f"{today.roas:.2f}" if today.roas else "N/A"
    parts.append(f"【当日】花费${today.spend:.0f}，ROI {today_roas_str}，购买{today.purchase:.0f}单")
    
    # ATC%和Checkout%对比7天
    if avg_7d and avg_7d.atc_rate and avg_7d.checkout_rate:
        today_atc = today.atc_rate
        today_checkout = today.checkout_rate
        if today_atc and avg_7d.atc_rate and avg_7d.atc_rate > 0:
            atc_change = (today_atc - avg_7d.atc_rate) / avg_7d.atc_rate * 100
            atc_str = f"ATC率{today_atc*100:.1f}%（较7天{'↑' if atc_change > 0 else '↓'}{abs(atc_change):.0f}%）"
            parts.append(atc_str)
        if today_checkout and avg_7d.checkout_rate and avg_7d.checkout_rate > 0:
            checkout_change = (today_checkout - avg_7d.checkout_rate) / avg_7d.checkout_rate * 100
            checkout_str = f"Checkout率{today_checkout*100:.1f}%（较7天{'↑' if checkout_change > 0 else '↓'}{abs(checkout_change):.0f}%）"
            parts.append(checkout_str)
    
    # 2. 3天数据
    last_3d_roas_str = f"{last_3d.roas:.2f}" if last_3d.roas else "N/A"
    parts.append(f"【3日】花费${last_3d.spend:.0f}，ROI {last_3d_roas_str}，购买{last_3d.purchase:.0f}单")
    
    # 3. 7天数据
    if avg_7d:
        avg_7d_roas_str = f"{avg_7d.roas:.2f}" if avg_7d.roas else "N/A"
        parts.append(f"【7日】花费${avg_7d.spend:.0f}，ROI {avg_7d_roas_str}，购买{avg_7d.purchase:.0f}单")
    
    # 4. 规则命中（核心）
    rule_parts = []
    
    # 场景
    scene_map = {
        "scene_1_today_pass_3d_pass": "场景1：当天达标+3天达标",
        "scene_2_today_pass_3d_neutral": "场景2：当天达标+3天一般",
        "scene_3_today_pass_3d_below": "场景3：当天达标+3天较差",
        "scene_4_today_neutral_3d_pass": "场景4：当天一般+3天达标",
        "scene_5_today_below_3d_pass": "场景5：当天较差+3天达标",
        "scene_6_today_neutral_3d_neutral": "场景6：当天一般+3天一般",
        "scene_7_today_below_3d_neutral": "场景7：当天较差+3天一般",
        "scene_8_today_below_3d_below": "场景8：当天较差+3天较差",
        "brand": "Brand账户规则",
        "data_insufficient": "数据不足规则",
        "data_error": "数据异常规则",
        "regime_error": "实体状态异常",
    }
    scene_name = scene_map.get(scene, scene)
    rule_parts.append(scene_name)
    
    # 实体状态
    regime_map = {
        "BULL": "实体状态：BULL（超标20%+）",
        "HEALTHY": "实体状态：HEALTHY（达标）",
        "NEUTRAL": "实体状态：NEUTRAL（差一点达标）",
        "BEAR": "实体状态：BEAR（较差）",
        "SEVERE_BEAR": "实体状态：SEVERE_BEAR（很差）",
    }
    regime_name = regime_map.get(entity_regime, f"实体状态：{entity_regime}")
    rule_parts.append(regime_name)
    
    # 账户模式
    mode_map = {
        "aggressive": "账户模式：aggressive（放量）",
        "normal": "账户模式：normal（正常）",
        "conservative": "账户模式：conservative（保守）",
    }
    mode_name = mode_map.get(account_mode, f"账户模式：{account_mode}")
    rule_parts.append(mode_name)
    
    parts.append(f"【命中规则】{' + '.join(rule_parts)}")
    
    # 5. 动作说明
    base_pct = pct_from_action(base_action)
    final_pct = pct_from_action(final_action)
    
    if final_action in NO_WRITE_ACTIONS:
        if final_action == "COOLDOWN":
            action_str = f"最终动作：COOLDOWN（冷却期，不调整）"
        elif final_action == "NO_CHANGE":
            action_str = f"最终动作：NO_CHANGE（不调整）"
        else:
            action_str = f"最终动作：{final_action}"
    else:
        action_str = f"基础动作：{base_action}（{base_pct*100:+.0f}%）"
        if base_action != final_action:
            action_str += f" → 最终动作：{final_action}（{final_pct*100:+.0f}%）"
        else:
            action_str += f"，最终动作：{final_action}"
    
    parts.append(f"【动作】{action_str}")
    
    # 6. 其他原因
    if reason_parts:
        parts.append("【补充】" + "；".join(reason_parts))
    
    return "；".join(parts)
    hint = ""
    if funnel_anomaly:
        hint = (
            "Front-end conversion metrics are strong but did not convert to purchase. "
            "Manually check creative intent, Landing Page, Checkout, Pixel/CAPI, Attribution, and Meta Advantage+ settings."
        )
    new_budget = proposed_budget(current_budget, action, config)
    return {
        "proposed_action": action,
        "proposed_new_budget": str(new_budget) if new_budget is not None else None,
        "adjustment_percentage": str((pct_from_action(action) * Decimal("100")).quantize(Decimal("1"))) if action not in NO_WRITE_ACTIONS else "0",
        "reason": reason,
        "funnel_anomaly": "Yes" if funnel_anomaly else "No",
        "optimization_hint": hint or funnel_reason,
    }
