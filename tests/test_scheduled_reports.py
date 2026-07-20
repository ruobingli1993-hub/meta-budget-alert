from __future__ import annotations

import os
import json
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from config import AccountConfig
from meta_data_provider import AccountMeta, InsightRecord, PeriodSpec
from scheduled_reports import AccountReportRow, build_report_plan, ensure_schedule_fresh, format_report, judge_account, load_report_state, parse_as_of, performance_missing_reason, save_report_state, scheduled_time, write_log, write_skip_log


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
        self.assertIsNone(plan.current_period.date_preset)
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
        current = record(PERF, spend="100", purchase="2", value=None, roas=None)
        status, reason = judge_account(PERF, current, record(PERF, spend="100", value="250"), plan)
        rows = [AccountReportRow(PERF, META, current, record(PERF, spend="100", value="250"), None, status, reason)]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-10T09:00:00"
            text = format_report(plan, rows)
        self.assertIn("Performance ROAS: N/A", text)
        self.assertIn("ROAS N/A", text)
        self.assertNotIn("ROAS 0.00", text)
        self.assertIn("Purchase Value N/A", text)
        self.assertIn("Data Date 2026-07-10", text)
        self.assertIn("Account Timezone America/Phoenix", text)
        self.assertIn("Missing Reason: Purchase Value字段缺失", text)
        self.assertEqual(status, "DATA_ERROR")

    def test_realtime_missing_value_has_reason_and_seven_day_reference(self) -> None:
        plan = build_report_plan("morning", "America/Phoenix", datetime(2026, 7, 10, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        current = record(PERF, spend="100", purchase="2", value=None, roas=None)
        history = record(PERF, spend="100", purchase="2", value="320")
        status, reason = judge_account(PERF, current, history, plan)
        rows = [AccountReportRow(PERF, META, current, history, None, status, reason, history)]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-10T09:00:00"
            text = format_report(plan, rows)
        self.assertEqual(status, "DATA_INSUFFICIENT")
        self.assertIn("当日数据尚未完全回传：Purchase Value字段缺失", text)
        self.assertIn("Last 7 Complete Days ROAS: 3.20", text)

    def test_missing_reason_distinguishes_zero_spend_and_api_error(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 10, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(performance_missing_reason(record(PERF, spend="0", purchase="0", value="0"), plan), "Spend为0，无法计算ROAS")
        failed = record(PERF, spend=None, purchase=None, value=None, status="ERROR")
        self.assertIn("Meta接口失败", performance_missing_reason(failed, plan))

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

    def test_delayed_run_is_anchored_to_scheduled_slot(self) -> None:
        observed = datetime(2026, 7, 15, 23, 13, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(scheduled_time("early-pulse", observed).isoformat(), "2026-07-15T18:00:00+08:00")
        after_midnight = datetime(2026, 7, 16, 0, 13, 45, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.assertEqual(scheduled_time("early-pulse", after_midnight).isoformat(), "2026-07-15T18:00:00+08:00")

    def test_stale_scheduled_report_is_suppressed(self) -> None:
        planned = datetime(2026, 7, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch.dict(os.environ, {}, clear=True):
            ensure_schedule_fresh(planned, datetime(2026, 7, 16, 9, 29, tzinfo=ZoneInfo("Asia/Shanghai")))
            with self.assertRaisesRegex(RuntimeError, "Stale scheduled report suppressed"):
                ensure_schedule_fresh(planned, datetime(2026, 7, 16, 17, 29, tzinfo=ZoneInfo("Asia/Shanghai")))

    def test_manual_dispatch_can_allow_stale_report(self) -> None:
        planned = datetime(2026, 7, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        actual = datetime(2026, 7, 16, 17, 29, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch.dict(os.environ, {"ALLOW_STALE_SCHEDULED_REPORT": "true"}, clear=True):
            ensure_schedule_fresh(planned, actual)

    def test_expected_windows_for_july_16_beijing_slots(self) -> None:
        tz = ZoneInfo("Asia/Shanghai")
        morning = build_report_plan("morning", "America/Phoenix", datetime(2026, 7, 16, 9, 0, tzinfo=tz))
        close = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 16, 15, 30, tzinfo=tz))
        pulse = build_report_plan("early-pulse", "America/Phoenix", datetime(2026, 7, 16, 18, 0, tzinfo=tz))
        self.assertEqual((morning.current_period.since, morning.account_local_time.hour), ("2026-07-15", 18))
        self.assertEqual((close.current_period.since, close.current_period.until), ("2026-07-15", "2026-07-15"))
        self.assertEqual((pulse.current_period.since, pulse.account_local_time.hour), ("2026-07-16", 3))

    def test_report_labels_total_as_multi_account_and_fixed_window(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 16, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        rows = [AccountReportRow(PERF, META, record(PERF), None, None, "HEALTHY", "ok")]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-16T09:00:00"
            text = format_report(plan, rows)
        self.assertIn("Data window: account date 2026-07-15, complete day", text)
        self.assertIn("Total Spend (1 accounts): $100.00", text)

    def test_multi_account_total_matches_account_spend_lines(self) -> None:
        plan = build_report_plan("daily-close", "America/Phoenix", datetime(2026, 7, 16, 15, 30, tzinfo=ZoneInfo("Asia/Shanghai")))
        rows = [
            AccountReportRow(PERF, META, record(PERF, spend="100"), None, None, "HEALTHY", "ok"),
            AccountReportRow(AccountConfig("Performance 2", "3", "performance"), META, record(AccountConfig("Performance 2", "3", "performance"), spend="50"), None, None, "HEALTHY", "ok"),
            AccountReportRow(BRAND, META, record(BRAND, spend="25", purchase="0", value="0"), None, None, "HEALTHY", "ok"),
        ]
        with patch("scheduled_reports.load_preview") as fake_preview:
            fake_preview.return_value.suggestions = []
            fake_preview.return_value.run_id = "budget_test"
            fake_preview.return_value.created_at = "2026-07-16T09:00:00"
            text = format_report(plan, rows)
        self.assertIn("Total Spend (3 accounts): $175.00", text)
        self.assertIn("Performance: HEALTHY | Spend $100.00", text)
        self.assertIn("Performance 2: HEALTHY | Spend $50.00", text)
        self.assertIn("Brand: HEALTHY | Spend $25.00", text)

    def test_scheduled_report_log_contains_delivery_and_account_spend_fields(self) -> None:
        plan = build_report_plan("morning", "America/Phoenix", datetime(2026, 7, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
        current = record(PERF, spend="123")
        current = InsightRecord(**{**current.__dict__, "raw_spend": "123"})
        rows = [AccountReportRow(PERF, META, current, None, None, "HEALTHY", "ok")]
        with patch("scheduled_reports.SCHEDULED_REPORT_LOG", Path("logs/test_scheduled_reports.log")) as fake_path:
            if fake_path.exists():
                fake_path.unlink()
            write_log(plan, rows, "SUCCESS", datetime(2026, 7, 16, 9, 2, 5, tzinfo=ZoneInfo("Asia/Shanghai")))
            payload = json.loads(fake_path.read_text(encoding="utf-8").strip())
            fake_path.unlink()
        self.assertEqual(payload["message_type"], "scheduled_report")
        self.assertEqual(payload["scheduler_delay_seconds"], 125)
        self.assertEqual(payload["query_date"], "2026-07-15")
        self.assertEqual(payload["cutoff_hour"], 18)
        self.assertEqual(payload["accounts"][0]["raw_spend"], "123")
        self.assertEqual(payload["accounts"][0]["purchase_value"], "300")
        self.assertEqual(payload["accounts"][0]["roas"], str(Decimal("300") / Decimal("123")))
        self.assertEqual(payload["feishu_send_result"], "SUCCESS")

    def test_report_state_round_trip_and_skip_log_run_key(self) -> None:
        state_path = Path("logs/test_scheduled_report_state.json")
        log_path = Path("logs/test_scheduled_reports_skip.log")
        for path in (state_path, log_path):
            if path.exists():
                path.unlink()
        with patch("scheduled_reports.SCHEDULED_REPORT_STATE", state_path), patch("scheduled_reports.SCHEDULED_REPORT_LOG", log_path):
            save_report_state({"runs": {"2026-07-16:morning": {"status": "SENT"}}})
            self.assertEqual(load_report_state()["runs"]["2026-07-16:morning"]["status"], "SENT")
            planned = datetime(2026, 7, 16, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
            write_skip_log("morning", planned, planned, "2026-07-16:morning", "already_sent")
            payload = json.loads(log_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["run_key"], "2026-07-16:morning")
            self.assertEqual(payload["send_status"], "SKIPPED")
            self.assertEqual(payload["skip_reason"], "already_sent")
        state_path.unlink()
        log_path.unlink()

    def test_github_cron_and_dispatch(self) -> None:
        workflow = Path(".github/workflows/scheduled_reports.yml").read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn('cron: "0 1 * * *"', workflow)
        self.assertIn('cron: "30 7 * * *"', workflow)
        self.assertIn('cron: "0 10 * * *"', workflow)
        self.assertIn("report_mode:", workflow)
        self.assertIn("ALLOW_STALE_SCHEDULED_REPORT:", workflow)
        self.assertIn("scheduled-meta-reports-production", workflow)
        self.assertIn("scheduled-report-state-", workflow)
        self.assertIn("triggered_at:", workflow)


if __name__ == "__main__":
    unittest.main()
