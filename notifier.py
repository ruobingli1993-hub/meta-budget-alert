from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from feishu import FeishuWebhookClient
from meta_api import AccountBudgetSnapshot
from chinese_holidays import HolidayRechargeRisk


def money(value: Decimal, currency: str) -> str:
    normalized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    symbol = "$" if currency.upper() == "USD" else f"{currency.upper()} "
    return f"{symbol}{normalized}"


def build_alert_message(snapshot: AccountBudgetSnapshot, holiday_risk: HolidayRechargeRisk | None = None) -> str:
    days = (
        f"{snapshot.estimated_days_remaining:.2f}"
        if snapshot.estimated_days_remaining is not None
        else "N/A"
    )
    holiday_lines = []
    if holiday_risk:
        holiday_lines = [
            "",
            f"Holiday Risk: {holiday_risk.holiday.name} ({holiday_risk.holiday.start.isoformat()} to {holiday_risk.holiday.end.isoformat()})",
            f"Coverage Required: {holiday_risk.required_days} days through {holiday_risk.next_recharge_workday.isoformat()} plus 1-day buffer",
        ]
    return "\n".join(
        [
            "Meta Budget Alert",
            "",
            f"Account: {snapshot.account.name}",
            f"Account ID: {snapshot.account.account_id}",
            f"Current Balance: {money(snapshot.current_balance, snapshot.currency)}",
            f"Last 7 Complete Days Avg Daily Spend: {money(snapshot.average_daily_spend, snapshot.currency)}",
            f"3-Day Threshold: {money(snapshot.threshold, snapshot.currency)}",
            f"Estimated Days Remaining: {days}",
            *holiday_lines,
            "",
            "Trigger Reason: Holiday coverage risk." if holiday_risk else "Trigger Reason: Current balance is at or below the estimated 3-day spend threshold.",
            "Action: Please recharge this Meta ad account.",
        ]
    )


class BudgetAlertNotifier:
    def __init__(self, feishu_client: FeishuWebhookClient) -> None:
        self.feishu_client = feishu_client

    def send_budget_alert(self, snapshot: AccountBudgetSnapshot, holiday_risk: HolidayRechargeRisk | None = None) -> dict[str, object]:
        return self.feishu_client.send_text(build_alert_message(snapshot, holiday_risk))
