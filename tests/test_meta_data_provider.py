from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from config import AccountConfig
from meta_api import MetaAPIError
from meta_data_provider import (
    AccountMeta,
    InsightRecord,
    MetaDataProvider,
    PeriodSpec,
    action_types,
    empty_record,
    error_record,
    extract_learning_status,
    record_from_row,
    sum_records,
)
from morning_report import metric_from_record
from skills.budget_manager import analyzer, rules


ACCOUNT = AccountConfig(name="QMDT-20240103", account_id="750289240467952", account_type="performance")
META = AccountMeta(
    account_id=ACCOUNT.account_id,
    account_name=ACCOUNT.name,
    api_id=ACCOUNT.api_id,
    currency="USD",
    timezone_name="America/Los_Angeles",
    timezone_offset_hours_utc="-7",
    account_today=date(2026, 7, 10),
)
TODAY = PeriodSpec(period="today", since="2026-07-10", until="2026-07-10", date_preset="today", includes_today=True)
LAST_3D = PeriodSpec(period="last_3_complete_days", since="2026-07-07", until="2026-07-09")


class FakeAPI:
    base_url = "https://graph.facebook.com/v20.0"
    access_token = "test-token"

    def __init__(self) -> None:
        self.requests = []

    def _request(self, method, url, params):
        self.requests.append({"method": method, "url": url, "params": params})
        if url.endswith(ACCOUNT.api_id):
            return {"currency": "USD", "timezone_name": "America/Los_Angeles", "timezone_offset_hours_utc": -7}
        return {"data": []}


class ErrorAPI(FakeAPI):
    def _request(self, method, url, params):
        if url.endswith("/insights"):
            raise MetaAPIError("Permission error", http_status_code=400, meta_error_code=190)
        return super()._request(method, url, params)


class MetaDataProviderTest(unittest.TestCase):
    def test_today_uses_date_preset_and_account_timezone(self) -> None:
        api = FakeAPI()
        provider = MetaDataProvider(api)  # type: ignore[arg-type]
        provider.get_insights(ACCOUNT, "account", "today", meta=META)
        request = api.requests[-1]["params"]
        self.assertEqual(request["date_preset"], "today")
        self.assertNotIn("time_range", request)

    def test_last_3_complete_days_range_excludes_today(self) -> None:
        provider = MetaDataProvider(FakeAPI())  # type: ignore[arg-type]
        period = provider.period(META, "last_3_complete_days")
        self.assertEqual(period.since, "2026-07-07")
        self.assertEqual(period.until, "2026-07-09")

    def test_qmdt_account_roas_parses_from_purchase_value(self) -> None:
        record = record_from_row(
            META,
            "account",
            LAST_3D,
            {
                "spend": "100",
                "actions": [{"action_type": "purchase", "value": "2"}],
                "action_values": [{"action_type": "purchase", "value": "350"}],
                "clicks": "10",
                "impressions": "1000",
                "reach": "800",
            },
            ACCOUNT.api_id,
            ACCOUNT.name,
        )
        self.assertEqual(record.purchase, Decimal("2"))
        self.assertEqual(record.purchase_value, Decimal("350"))
        self.assertEqual(record.roas, Decimal("3.5"))

    def test_hourly_sum_ignores_missing_purchase_value_when_hour_has_no_purchase(self) -> None:
        period = PeriodSpec("today_same_time", "2026-07-20", "2026-07-20")
        purchase_hour = record_from_row(
            META,
            "account",
            period,
            {
                "spend": "100",
                "actions": [{"action_type": "purchase", "value": "2"}],
                "action_values": [{"action_type": "purchase", "value": "300"}],
            },
            ACCOUNT.account_id,
            ACCOUNT.name,
        )
        no_purchase_hour = record_from_row(
            META,
            "account",
            period,
            {"spend": "50", "actions": [], "action_values": []},
            ACCOUNT.account_id,
            ACCOUNT.name,
        )

        combined = sum_records([purchase_hour, no_purchase_hour], "account", period.period)

        self.assertEqual(combined.purchase, Decimal("2"))
        self.assertEqual(combined.purchase_value, Decimal("300"))
        self.assertEqual(combined.roas, Decimal("2"))

    def test_hourly_sum_keeps_purchase_value_missing_when_purchase_hour_has_no_value(self) -> None:
        period = PeriodSpec("today_same_time", "2026-07-20", "2026-07-20")
        missing_value_hour = record_from_row(
            META,
            "account",
            period,
            {
                "spend": "100",
                "actions": [{"action_type": "purchase", "value": "2"}],
                "action_values": [],
            },
            ACCOUNT.account_id,
            ACCOUNT.name,
        )

        combined = sum_records([missing_value_hour], "account", period.period)

        self.assertIsNone(combined.purchase_value)
        self.assertIsNone(combined.roas)

    def test_purchase_event_priority_does_not_double_count(self) -> None:
        record = record_from_row(
            META,
            "account",
            TODAY,
            {
                "spend": "100",
                "actions": [
                    {"action_type": "purchase", "value": "1"},
                    {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "99"},
                    {"action_type": "omni_purchase", "value": "88"},
                ],
                "action_values": [
                    {"action_type": "purchase", "value": "200"},
                    {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "999"},
                ],
            },
            ACCOUNT.api_id,
            ACCOUNT.name,
        )
        self.assertEqual(record.purchase, Decimal("1"))
        self.assertEqual(record.purchase_value, Decimal("200"))
        self.assertEqual(record.selected_purchase_action_type, "purchase")
        self.assertEqual(action_types(record.raw_rows_sample[0]["actions"]), ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase"))

    def test_native_purchase_roas_does_not_fabricate_missing_purchase_value(self) -> None:
        record = record_from_row(
            META,
            "account",
            TODAY,
            {
                "spend": "100",
                "actions": [{"action_type": "purchase", "value": "2"}],
                "action_values": [],
                "purchase_roas": [{"action_type": "omni_purchase", "value": "3.25"}],
            },
            ACCOUNT.api_id,
            ACCOUNT.name,
        )
        self.assertIsNone(record.roas)
        self.assertIsNone(record.purchase_value)
        self.assertEqual(record.raw_purchase_roas_types, ("omni_purchase",))

    def test_api_error_does_not_become_zero(self) -> None:
        provider = MetaDataProvider(ErrorAPI())  # type: ignore[arg-type]
        record = provider.get_insights(ACCOUNT, "account", "today", meta=META)[0]
        self.assertEqual(record.data_status, "ERROR")
        self.assertIsNone(record.spend)
        self.assertEqual(record.http_status_code, 400)
        self.assertEqual(record.meta_error_code, 190)

    def test_empty_data_is_marked_empty(self) -> None:
        record = empty_record(META, "account", ACCOUNT.api_id, ACCOUNT.name, TODAY)
        self.assertEqual(record.data_status, "EMPTY")
        self.assertEqual(record.spend, Decimal("0"))
        self.assertIsNone(record.purchase_value)
        self.assertIsNone(record.roas)

    def test_account_regime_roas_none_is_data_insufficient(self) -> None:
        config = rules.load_config()
        three_day = empty_record(META, "account", ACCOUNT.api_id, ACCOUNT.name, LAST_3D)
        today = empty_record(META, "account", ACCOUNT.api_id, ACCOUNT.name, TODAY)
        regime, _ = analyzer.account_regime_from_records(
            three_day,
            today,
            analyzer.metric_window(three_day),
            analyzer.metric_window(today),
            False,
            config,
        )
        self.assertEqual(regime, "DATA_INSUFFICIENT")

    def test_learning_status_never_uses_fail_success(self) -> None:
        self.assertEqual(extract_learning_status({"learning_stage_info": {"status": "FAIL"}}), "N/A")
        self.assertEqual(extract_learning_status({"learning_stage_info": {"status": "SUCCESS"}}), "N/A")
        self.assertEqual(extract_learning_status({"learning_stage_info": {"status": "LEARNING_LIMITED"}}), "Learning Limited")

    def test_morning_report_and_budget_manager_share_same_record_values(self) -> None:
        record = record_from_row(
            META,
            "account",
            TODAY,
            {
                "spend": "123.45",
                "actions": [{"action_type": "purchase", "value": "3"}, {"action_type": "link_click", "value": "50"}],
                "action_values": [{"action_type": "purchase", "value": "456.78"}],
                "clicks": "70",
                "impressions": "1000",
                "reach": "900",
            },
            ACCOUNT.api_id,
            ACCOUNT.name,
        )
        morning = metric_from_record(record)
        budget = analyzer.metric_window(record)
        self.assertEqual(morning.spend, budget.spend)
        self.assertEqual(morning.purchase, budget.purchase)
        self.assertEqual(morning.revenue, budget.purchase_value)
        self.assertEqual(morning.roas, budget.roas)


if __name__ == "__main__":
    unittest.main()
