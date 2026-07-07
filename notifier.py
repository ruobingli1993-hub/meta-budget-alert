from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from feishu import FeishuWebhookClient
from meta_api import AccountBudgetSnapshot


def money(value: Decimal, currency: str) -> str:
    normalized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    symbol = "$" if currency.upper() == "USD" else f"{currency.upper()} "
    return f"{symbol}{normalized}"


def build_alert_message(snapshot: AccountBudgetSnapshot) -> str:
    account = snapshot.account
    return "\n".join(
        [
            "【Meta广告预算预警】",
            "",
            "账户：",
            account.name,
            "",
            "账户ID：",
            account.account_id,
            "",
            "当前余额：",
            money(snapshot.current_balance, snapshot.currency),
            "",
            "过去7天平均日花费：",
            money(snapshot.average_daily_spend, snapshot.currency),
            "",
            "预警阈值（3天）：",
            money(snapshot.threshold, snapshot.currency),
            "",
            "状态：",
            "⚠ 当前余额已低于过去7天平均日花费的3倍，请及时充值。",
        ]
    )


class BudgetAlertNotifier:
    def __init__(self, feishu_client: FeishuWebhookClient) -> None:
        self.feishu_client = feishu_client

    def send_budget_alert(self, snapshot: AccountBudgetSnapshot) -> None:
        self.feishu_client.send_text(build_alert_message(snapshot))
