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


def has_last_3d_sample(metrics: MetricWindow, config: dict[str, Any]) -> bool:
    sample = config["sample_protection"]
    return metrics.spend >= Decimal(str(sample["last_3d_spend_min"])) or metrics.purchase >= Decimal(str(sample["last_3d_purchase_min"]))


def has_today_sample(metrics: MetricWindow, config: dict[str, Any]) -> bool:
    sample = config["sample_protection"]
    return metrics.spend >= Decimal(str(sample["today_spend_min"])) or metrics.purchase >= Decimal(str(sample["today_purchase_min"]))


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


def learning_limited_action(action: str) -> str:
    if action in {"INCREASE_25", "INCREASE_20", "INCREASE_15"}:
        return "INCREASE_10"
    if action in {"DECREASE_25", "DECREASE_20", "DECREASE_15"}:
        return "DECREASE_10"
    return action


def evaluate_entity(
    entity_level: str,
    budget_model: str,
    rtg: bool,
    account_regime: str,
    last_3d: MetricWindow,
    today: MetricWindow,
    avg_30d: MetricWindow,
    current_budget: Decimal | None,
    learning_status: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    funnel_anomaly, funnel_reason = detect_funnel_anomaly(today, avg_30d, config)
    if not has_last_3d_sample(last_3d, config) or not has_today_sample(today, config):
        return decision("DATA_INSUFFICIENT", current_budget, config, "Data sample is insufficient.", funnel_anomaly, funnel_reason)
    if last_3d.roas is None or today.roas is None:
        return decision("DATA_ERROR", current_budget, config, "Purchase value or ROAS is unavailable.", funnel_anomaly, funnel_reason)
    if funnel_anomaly:
        return decision("NO_CHANGE", current_budget, config, "Funnel Anomaly blocks budget increase.", funnel_anomaly, funnel_reason)
    if account_regime in {"DATA_INSUFFICIENT", "DATA_ERROR"}:
        return decision(account_regime, current_budget, config, "Account regime blocks budget changes.", funnel_anomaly, funnel_reason)

    action = "NO_CHANGE"
    reason = "Default NO_CHANGE."
    if budget_model == "ABO" and entity_level == "Ad Set":
        if last_3d.roas < Decimal("2.0") and today.roas <= Decimal("2.0"):
            action = config["actions_by_regime"]["abo_decrease"].get(account_regime, "NO_CHANGE")
            reason = "ABO Ad Set 3D and today ROAS are both low."
        elif last_3d.roas < Decimal("2.0") and today.roas > Decimal("2.0"):
            reason = "Today performance recovered; no decrease."
    elif budget_model == "CBO" and entity_level == "Campaign" and rtg:
        if last_3d.roas > Decimal("3.5") and last_3d.purchase >= Decimal("2") and today.roas >= Decimal("3.0") and today.purchase >= Decimal("1"):
            action = config["actions_by_regime"]["rtg_cbo_increase"].get(account_regime, "NO_CHANGE")
            reason = "RTG CBO meets increase conditions."
    elif budget_model == "CBO" and entity_level == "Campaign":
        if last_3d.roas > Decimal("2.5") and today.roas > Decimal("2.5") and last_3d.purchase >= Decimal("2") and today.purchase >= Decimal("1"):
            action = config["actions_by_regime"]["non_rtg_cbo_increase"].get(account_regime, "NO_CHANGE")
            reason = "Non-RTG CBO meets increase conditions."
        elif last_3d.roas < Decimal("2.0") and today.roas < Decimal("2.0"):
            action = config["actions_by_regime"]["non_rtg_cbo_decrease"].get(account_regime, "NO_CHANGE")
            reason = "Non-RTG CBO 3D and today ROAS are both low."
        else:
            reason = "3D and today direction are inconsistent or conditions are not met."

    if learning_status.lower() in {"learning", "learning limited", "learning_limited"}:
        original = action
        action = learning_limited_action(action)
        if original != action:
            reason = f"Learning status caps the adjustment at 10%; original action was {original}."
        elif action != "NO_CHANGE":
            reason = "Learning status allows only a small adjustment."

    return decision(action, current_budget, config, reason, funnel_anomaly, funnel_reason)


def decision(action: str, current_budget: Decimal | None, config: dict[str, Any], reason: str, funnel_anomaly: bool, funnel_reason: str) -> dict[str, Any]:
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
