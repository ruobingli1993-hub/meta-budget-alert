from __future__ import annotations

import os
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from config import AccountConfig
from meta_data_provider import AccountMeta, InsightRecord, PeriodSpec
from scheduled_reports import AccountReportRow, build_report_plan, format_report, judge_account, parse_as_of


PERF = AccountConfig("Performance", "1", "performance")
BRAND = AccountConfig("Brand", "2", "brand")
META = AccountMeta("1", "Performance", "act_1", "USD", "America/Phoenix", "-7", datetime(2026, 7, 10).date())


def record(account, spend="100", purchase="2", value="300", roas=None, status="SUCCESS", ctr="0.02", frequency="1.5") -> InsightRecord:
    spend_d = Decimal(spend) if spend is not None else None
    value_d = Decimal(value) if value is not None else None
    roas_d = Decimal(roas) if roas is not None else (value_d / spend_d if spend_d and value_d is not None else None)
    return InsightRecord(
        account_id=account.account_id,
        account_name=account.name,
        timezone="America/Phoenix",
        timezone_offset_hours_utc="-7",
        currency="USD",
        level="account",
        entity_id=account.account_id,
        entity_name=account.name,
        period="test",
        since="2026-07-10",
        until="2026-07-10",
        date_preset="today",
        spend=spend_d,
        purchase=Decimal(purchase) if purchase is not None else None,
        purchase_value=value_d,
        roas=roas_d,
        impressions=Decimal("10000"),
        clicks=Decimal("200"),
        link_clicks=Decimal("180"),
        reach=Decimal("7000"),
        ctr=Decimal(ctr) if ctr is not None else None,
        frequency=Decimal(frequency) if frequency is not None else None,
        add_to_cart=Decimal("4"),
        checkout=Decimal("3"),
        data_status=status,
        error="failed" if status == "ERROR" else None,
    )


class ScheduledReportsTest(unittest.TestCase):
    def test_morning_uses_same_time_window(self) -> None:
        plan = build_report_plan("morning", "America/Phoenix", datetime(2026, 7, 10, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertTrue(plan.same_time_window)
        self.assertEqual(plan.current_period.date_preset, "today")
        self.assertEqual(plan.account_local_time.hour, 18)
        self.assertEqual(plan.comparison_7d.since, "2026-07-02")

    def test_daily_close_uses_previous_complete_day(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertFalse(plan.same_time_window)
        self.assertEqual(plan.current_period.since, "2026-07-09")
        self.assertEqual(plan.current_period.until, "2026-07-09")

    def test_early_pulse_uses_early_same_time_window(self) -> None:
        plan = build_report_plan("early-pulse", "America/Phoenix", datetime(2026, 7, 10, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertTrue(plan.same_time_window)
        self.assertEqual(plan.account_local_time.hour, 3)
        self.assertEqual(plan.confidence_floor, "LOW")

    def test_phoenix_date_switch(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(plan.account_local_time.date().isoformat(), "2026-07-10")

    def test_brand_account_does_not_use_roas(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        status, _ = judge_account(BRAND, record(BRAND, value=None, roas=None, ctr="0.03"), record(BRAND, ctr="0.02"), plan)
        self.assertEqual(status, "HEALTHY")

    def test_brand_reach_or_frequency_missing_is_insufficient(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        weak_record = record(BRAND, value=None, roas=None)
        weak_record = InsightRecord(**{**weak_record.__dict__, "reach": Decimal("0"), "frequency": None})
        status, _ = judge_account(BRAND, weak_record, record(BRAND), plan)
        self.assertEqual(status, "DATA_INSUFFICIENT")

    def test_performance_and_all_account_roas_are_separate(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        rows = [
            AccountReportRow(PERF, META, record(PERF, spend="100", value="300"), None, None, "HEALTHY", "ok"),
            AccountReportRow(BRAND, META, record(BRAND, spend="100", purchase="0", value="0"), None, None, "HEALTHY", "ok"),
        ]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-10T09:00:00"
            text = format_report(plan, rows)
        self.assertNotIn("All-account Blended ROAS", text)
        self.assertIn("Performance ROAS: 3.00", text)

    def test_low_confidence_and_missing_performance_roas_is_insufficient(self) -> None:
        plan = build_report_plan("early-pulse", "America/Phoenix", datetime(2026, 7, 10, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        rows = [AccountReportRow(PERF, META, record(PERF, spend="10", purchase="0", value=None, roas=None), None, None, "DATA_INSUFFICIENT", "low")]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-10T09:00:00"
            text = format_report(plan, rows)
        self.assertIn("Overall Status: DATA_INSUFFICIENT", text)
        self.assertNotIn("Overall Status: HEALTHY", text)

    def test_purchase_value_missing_shows_revenue_and_roas_na(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        rows = [AccountReportRow(PERF, META, record(PERF, spend="100", purchase="2", value=None, roas=None), None, None, "DATA_INSUFFICIENT", "missing value")]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-10T09:00:00"
            text = format_report(plan, rows)
        self.assertIn("Performance ROAS: N/A", text)
        self.assertIn("ROAS N/A", text)
        self.assertNotIn("ROAS 0.00", text)

    def test_api_failure_not_zero_and_dashboard_url_missing(self) -> None:
        plan = build_report_plan("morning", "America/Phoenix", datetime(2026, 7, 10, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        failed = record(PERF, spend=None, purchase=None, value=None, status="ERROR")
        rows = [AccountReportRow(PERF, None, failed, None, None, "DATA_ERROR", "failed")]
        with patch.dict(os.environ, {}, clear=True), patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_old"
            fake_preview.return_value.created_at = "2026-07-09T09:00:00"
            text = format_report(plan, rows)
        self.assertIn("Overall Status: DATA_INSUFFICIENT", text)
        self.assertIn("Dashboard URL not configured", text)
        self.assertNotIn("Spend $0.00", text)
        self.assertIn("Review RUN_ID: budget_old", text)
        self.assertIn("Review data generated at: 2026-07-09T09:00:00", text)

    def test_as_of_parses_offset_datetime(self) -> None:
        parsed = parse_as_of("2026-07-10T18:00:00-07:00")
        self.assertEqual(parsed.astimezone(ZoneInfo("America/Phoenix")).hour, 18)

    def test_github_cron_and_dispatch(self) -> None:
        workflow = Path(".github/workflows/scheduled_reports.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('cron: "0 1 * * *"', workflow)
        self.assertIn('cron: "30 7 * * *"', workflow)
        self.assertIn('cron: "0 10 * * *"', workflow)
        self.assertIn("report_mode:", workflow)


if __name__ == "__main__":
    unittest.main()
