from __future__ import annotations

import unittest
from unittest import mock
from datetime import datetime, timedelta
from decimal import Decimal

from config import AccountConfig
from meta_api import AccountBudgetSnapshot, MetaMarketingAPI
from meta_api import MetaAPIError
from main import BEIJING_TZ, budget_alert_run_context, build_budget_alert_decision, run_check_budget, run_check_budget_debug, update_account_state
from notifier import build_alert_message
from feishu import FeishuError


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


class EmptySpendBudgetAPI(FakeBudgetAPI):
    def _get_last_7_complete_days_spend(self, account, account_info):
        raise MetaAPIError("Meta API returned no last 7 complete days spend rows for Test")


class BudgetAlertTest(unittest.TestCase):
    def test_feishu_failure_rolls_back_prepared_alert_state(self) -> None:
        snapshot = AccountBudgetSnapshot(
            account=ACCOUNT, currency="USD", seven_day_spend=Decimal("700"),
            average_daily_spend=Decimal("100"), current_balance=Decimal("200"),
            threshold=Decimal("300"), account_spend_limit=Decimal("1000"), amount_spent=Decimal("800"),
        )
        state = {"accounts": {ACCOUNT.account_id: {"alerting": False}}}
        api = mock.Mock(); api.get_budget_snapshot.return_value = snapshot
        notifier = mock.Mock(); notifier.send_budget_alert.side_effect = FeishuError("failed")
        with mock.patch("main.validate_config"), \
            mock.patch("main.ACCOUNTS", [ACCOUNT]), \
            mock.patch("main.load_state", return_value=state), \
            mock.patch("main.save_state") as save_state, \
            mock.patch("main.MetaMarketingAPI", return_value=api), \
            mock.patch("main.BudgetAlertNotifier", return_value=notifier), \
            mock.patch("main.FeishuWebhookClient"), \
            mock.patch("main.append_budget_alert_log"):
            self.assertEqual(run_check_budget(), 1)
        self.assertFalse(state["accounts"][ACCOUNT.account_id]["alerting"])
        self.assertGreaterEqual(save_state.call_count, 3)

    def test_hourly_schedule_context_uses_minute_17(self) -> None:
        with mock.patch.dict("os.environ", {"BUDGET_ALERT_TRIGGER": "schedule", "WORKFLOW_CREATED_TIME": "2026-07-20T06:19:00Z"}, clear=False):
            context = budget_alert_run_context(datetime(2026, 7, 20, 14, 20, tzinfo=BEIJING_TZ))
        self.assertEqual(context["planned_beijing_time"], "2026-07-20T14:17:00+08:00")
        self.assertEqual(context["scheduler_delay_seconds"], 180)

    def test_recovery_skips_when_primary_succeeded_inside_hour(self) -> None:
        state = {"accounts": {}, "last_successful_check_at": datetime.now(BEIJING_TZ).isoformat()}
        with mock.patch.dict("os.environ", {"BUDGET_ALERT_TRIGGER": "recovery"}, clear=False), \
            mock.patch("main.validate_config"), \
            mock.patch("main.load_state", return_value=state), \
            mock.patch("main.save_state"), \
            mock.patch("main.MetaMarketingAPI") as api, \
            mock.patch("main.append_budget_alert_log"):
            self.assertEqual(run_check_budget(), 0)
        api.assert_not_called()

    def test_state_preflight_failure_stops_before_account_reads(self) -> None:
        with mock.patch("main.validate_config"), \
            mock.patch("main.load_state", return_value={"accounts": {}}), \
            mock.patch("main.save_state", side_effect=OSError("disk")), \
            mock.patch("main.MetaMarketingAPI") as api, \
            mock.patch("main.append_budget_alert_log"):
            self.assertEqual(run_check_budget(), 1)
        api.assert_not_called()

    def test_alert_message_only_contains_actionable_balance_fields(self) -> None:
        snapshot = AccountBudgetSnapshot(
            account=ACCOUNT,
            currency="USD",
            seven_day_spend=Decimal("2306.62"),
            average_daily_spend=Decimal("329.52"),
            current_balance=Decimal("916.25"),
            threshold=Decimal("988.55"),
            account_spend_limit=Decimal("140031"),
            amount_spent=Decimal("139114.75"),
        )
        message = build_alert_message(snapshot)
        self.assertIn("Current Balance: $916.25", message)
        self.assertIn("Estimated Days Remaining: 2.78", message)
        self.assertNotIn("Currency:", message)
        self.assertNotIn("Account Status:", message)
        self.assertNotIn("Spend Cap:", message)
        self.assertNotIn("Amount Spent:", message)

    def test_snapshot_uses_remaining_account_spend_limit(self) -> None:
        api = FakeBudgetAPI({
            "currency": "USD",
            "spend_cap": "2000000",
            "amount_spent": "1500000",
            "account_status": "1",
        })
        with mock.patch.object(api, "_account_today", return_value=datetime(2026, 7, 16).date()):
            snapshot = api.get_budget_snapshot(ACCOUNT)
        self.assertEqual(snapshot.account_spend_limit, Decimal("20000"))
        self.assertEqual(snapshot.amount_spent, Decimal("15000"))
        self.assertEqual(snapshot.current_balance, Decimal("5000"))
        self.assertEqual(snapshot.account_status, "1")
        self.assertEqual(snapshot.last_7_complete_days_range, {"since": "2026-07-09", "until": "2026-07-15"})

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

    def test_empty_last_7_days_spend_fails_closed(self) -> None:
        api = EmptySpendBudgetAPI({
            "currency": "USD",
            "spend_cap": "2000000",
            "amount_spent": "1500000",
        })
        with self.assertRaisesRegex(Exception, "no last 7 complete days spend rows"):
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

    def test_debug_mode_does_not_send_or_save_state(self) -> None:
        with mock.patch("main.META_ACCESS_TOKEN", "token"), \
            mock.patch("main.MetaMarketingAPI", return_value=FakeBudgetAPI({
                "currency": "USD",
                "spend_cap": "2000000",
                "amount_spent": "1500000",
            })), \
            mock.patch("main.load_state", return_value={"accounts": {}}) as load_state, \
            mock.patch("main.save_state") as save_state, \
            mock.patch("main.FeishuWebhookClient") as feishu, \
            mock.patch("main.append_budget_alert_debug_log"):
            self.assertEqual(run_check_budget_debug(), 0)
        load_state.assert_called_once()
        save_state.assert_not_called()
        feishu.assert_not_called()


if __name__ == "__main__":
    unittest.main()
