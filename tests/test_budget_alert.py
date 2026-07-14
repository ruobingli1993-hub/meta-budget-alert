from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from decimal import Decimal

from config import AccountConfig
from meta_api import AccountBudgetSnapshot, MetaMarketingAPI
from main import build_budget_alert_decision, update_account_state


ACCOUNT = AccountConfig("Test", "123", "performance")


class FakeBudgetAPI(MetaMarketingAPI):
    def __init__(self, account_info: dict[str, str]) -> None:
        self.account_info = account_info

    def _get_spend_limit_info(self, account):
        return self.account_info

    def _get_last_7_days_spend(self, account):
        return Decimal("700")

    def _get_last_7_complete_days_spend(self, account, account_info):
        return Decimal("700")


class BudgetAlertTest(unittest.TestCase):
    def test_snapshot_uses_remaining_account_spend_limit(self) -> None:
        api = FakeBudgetAPI({
            "currency": "USD",
            "spend_cap": "2000000",
            "amount_spent": "1500000",
            "account_status": "1",
        })
        snapshot = api.get_budget_snapshot(ACCOUNT)
        self.assertEqual(snapshot.account_spend_limit, Decimal("20000"))
        self.assertEqual(snapshot.amount_spent, Decimal("15000"))
        self.assertEqual(snapshot.current_balance, Decimal("5000"))
        self.assertEqual(snapshot.account_status, "1")

    def test_alerts_at_three_day_threshold(self) -> None:
        snapshot = AccountBudgetSnapshot(
            account=ACCOUNT,
            currency="USD",
            seven_day_spend=Decimal("700"),
            average_daily_spend=Decimal("100"),
            current_balance=Decimal("300"),
            threshold=Decimal("300"),
            account_spend_limit=Decimal("1000"),
            amount_spent=Decimal("700"),
        )
        self.assertTrue(snapshot.should_alert)
        self.assertEqual(snapshot.estimated_days_remaining, Decimal("3"))

    def test_missing_spend_limit_fails_closed(self) -> None:
        api = FakeBudgetAPI({"currency": "USD", "amount_spent": "1500000"})
        with self.assertRaisesRegex(Exception, "Spend cap is unavailable"):
            api.get_budget_snapshot(ACCOUNT)

    def test_decision_blocks_duplicate_inside_24_hours(self) -> None:
        snapshot = AccountBudgetSnapshot(
            account=ACCOUNT,
            currency="USD",
            seven_day_spend=Decimal("700"),
            average_daily_spend=Decimal("100"),
            current_balance=Decimal("200"),
            threshold=Decimal("300"),
            account_spend_limit=Decimal("1000"),
            amount_spent=Decimal("800"),
        )
        now = datetime(2026, 7, 14, 10, 0, 0)
        state = {"accounts": {ACCOUNT.account_id: {"alerting": True, "last_alert_sent_at": (now - timedelta(hours=2)).isoformat()}}}
        decision = build_budget_alert_decision(snapshot, state, now)
        self.assertTrue(decision.trigger_by_days)
        self.assertTrue(decision.trigger_by_amount)
        self.assertTrue(decision.de_duplication_would_block)
        self.assertFalse(decision.final_trigger)

    def test_decision_allows_repeat_after_24_hours(self) -> None:
        snapshot = AccountBudgetSnapshot(
            account=ACCOUNT,
            currency="USD",
            seven_day_spend=Decimal("700"),
            average_daily_spend=Decimal("100"),
            current_balance=Decimal("200"),
            threshold=Decimal("300"),
            account_spend_limit=Decimal("1000"),
            amount_spent=Decimal("800"),
        )
        now = datetime(2026, 7, 14, 10, 0, 0)
        state = {"accounts": {ACCOUNT.account_id: {"alerting": True, "last_alert_sent_at": (now - timedelta(hours=25)).isoformat()}}}
        decision = build_budget_alert_decision(snapshot, state, now)
        self.assertFalse(decision.de_duplication_would_block)
        self.assertTrue(decision.final_trigger)

    def test_recovery_clears_alerting_state(self) -> None:
        snapshot = AccountBudgetSnapshot(
            account=ACCOUNT,
            currency="USD",
            seven_day_spend=Decimal("700"),
            average_daily_spend=Decimal("100"),
            current_balance=Decimal("500"),
            threshold=Decimal("300"),
            account_spend_limit=Decimal("1000"),
            amount_spent=Decimal("500"),
        )
        state = {"accounts": {ACCOUNT.account_id: {"alerting": True, "last_alert_sent_at": "2026-07-14T08:00:00"}}}
        update_account_state(state, snapshot, alert_sent=False)
        self.assertFalse(state["accounts"][ACCOUNT.account_id]["alerting"])
        self.assertNotIn("last_alert_sent_at", state["accounts"][ACCOUNT.account_id])


if __name__ == "__main__":
    unittest.main()
