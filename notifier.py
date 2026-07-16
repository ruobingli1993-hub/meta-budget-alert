from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from feishu import FeishuWebhookClient
from meta_api import AccountBudgetSnapshot


def money(value: Decimal, currency: str) -> str:
    normalized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    symbol = "$" if currency.upper() == "USD" else f"{currency.upper()} "
    return f"{symbol}{normalized}"


def build_alert_message(snapshot: AccountBudgetSnapshot) -> str:
    days = (
        f"{snapshot.estimated_days_remaining:.2f}"
        if snapshot.estimated_days_remaining is not None
        else "N/A"
    )
    return "\n".join(
        [
            "Meta Budget Alert",
            "",
            f"Account: {snapshot.account.name}",
            f"Account ID: {snapshot.account.account_id}",
            f"Currency: {snapshot.currency}",
            f"Account Status: {snapshot.account_status}",
            f"Spend Cap: {money(snapshot.account_spend_limit, snapshot.currency)}",
            f"Amount Spent: {money(snapshot.amount_spent, snapshot.currency)}",
            f"Current Balance: {money(snapshot.current_balance, snapshot.currency)}",
            f"Last 7 Complete Days Avg Daily Spend: {money(snapshot.average_daily_spend, snapshot.currency)}",
            f"3-Day Threshold: {money(snapshot.threshold, snapshot.currency)}",
            f"Estimated Days Remaining: {days}",
            "",
            "Trigger Reason: Current balance is at or below the estimated 3-day spend threshold.",
            "Action: Please recharge this Meta ad account.",
        ]
    )


class BudgetAlertNotifier:
    def __init__(self, feishu_client: FeishuWebhookClient) -> None:
        self.feishu_client = feishu_client

    def send_budget_alert(self, snapshot: AccountBudgetSnapshot) -> None:
        self.feishu_client.send_text(build_alert_message(snapshot))
