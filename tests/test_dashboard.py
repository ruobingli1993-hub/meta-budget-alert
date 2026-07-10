from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dashboard import approval_store
from dashboard.approval_store import export_rejection_summary, save_approval
from dashboard.data_loader import (
    account_comparison_chart_data,
    approval_chart_data,
    build_feishu_daily_summary,
    dashboard_summary,
    filter_suggestions,
    load_preview,
    overall_summary,
    rule_feedback,
    trend_chart_data,
)


def sample_preview() -> dict:
    return {
        "run_id": "budget_test_001",
        "created_at": "2026-07-10T09:00:00",
        "recommendations": [
            {
                "account_name": "QMDT-20240103",
                "account_id": "750289240467952",
                "account_regime": "HEALTHY",
                "account_3d_roas": "3.20",
                "account_today_roas": "3.50",
                "entity_level": "Campaign",
                "campaign_name": "Campaign A",
                "campaign_id": "c1",
                "adset_name": None,
                "adset_id": None,
                "budget_model": "CBO",
                "rtg": "No",
                "delivery_status": "ACTIVE",
                "learning_status": "N/A",
                "current_budget": "100.00",
                "proposed_new_budget": "110.00",
                "adjustment_percentage": "10",
                "last_3d_spend": "300.00",
                "last_3d_purchase": "6.00",
                "last_3d_roas": "3.20",
                "today_spend": "80.00",
                "today_purchase": "2.00",
                "today_roas": "3.50",
                "funnel_anomaly": "No",
                "cooldown_status": "CLEAR",
                "data_confidence": "HIGH",
                "proposed_action": "INCREASE_10",
                "reason": "Meets rule",
                "optimization_hint": "",
            },
            {
                "account_name": "Sales Account",
                "account_id": "5600626876733411",
                "account_regime": "NEUTRAL",
                "account_3d_roas": "2.80",
                "account_today_roas": None,
                "entity_level": "Ad Set",
                "campaign_name": "Campaign B",
                "campaign_id": "c2",
                "adset_name": "Ad Set B",
                "adset_id": "a2",
                "budget_model": "ABO",
                "rtg": "No",
                "delivery_status": "ACTIVE",
                "learning_status": "Learning Limited",
                "current_budget": "100.00",
                "proposed_new_budget": None,
                "adjustment_percentage": "0",
                "last_3d_spend": "20.00",
                "last_3d_purchase": "0.00",
                "last_3d_roas": None,
                "today_spend": "0.00",
                "today_purchase": "0.00",
                "today_roas": None,
                "funnel_anomaly": "No",
                "cooldown_status": "CLEAR",
                "data_confidence": "LOW",
                "proposed_action": "DATA_INSUFFICIENT",
                "reason": "Sample low",
                "optimization_hint": "",
            },
        ],
    }


class DashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.preview_path = self.root / "budget_test_001.json"
        self.preview_path.write_text(json.dumps(sample_preview(), ensure_ascii=False, indent=2), encoding="utf-8")
        self.original_preview = self.preview_path.read_text(encoding="utf-8")
        self.approval_dir = self.root / "approvals"
        self.review_dir = self.root / "reviews"
        self.feedback_dir = self.root / "rule_feedback"
        self.log_path = self.root / "dashboard.log"
        self.patches = [
            patch.object(approval_store, "APPROVAL_DIR", self.approval_dir),
            patch.object(approval_store, "REVIEW_DIR", self.review_dir),
            patch.object(approval_store, "RULE_FEEDBACK_DIR", self.feedback_dir),
            patch.object(approval_store, "DASHBOARD_LOG", self.log_path),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def test_load_budget_preview_json(self) -> None:
        preview = load_preview(self.preview_path)
        self.assertEqual(preview.run_id, "budget_test_001")
        self.assertEqual(len(preview.suggestions), 2)

    def test_overall_summary_and_account_status(self) -> None:
        preview = load_preview(self.preview_path)
        summary = overall_summary(preview)
        self.assertEqual(summary["overall_spend"], "80.00")
        self.assertEqual(summary["overall_purchase"], "2.00")
        self.assertIn(summary["overall_data_confidence"], {"LOW", "HIGH"})

    def test_approve_save_success(self) -> None:
        suggestion = load_preview(self.preview_path).suggestions[0]
        record = save_approval(suggestion, "APPROVED")
        self.assertEqual(record.decision, "APPROVED")
        self.assertTrue((self.approval_dir / "budget_test_001.json").exists())

    def test_reject_requires_reason(self) -> None:
        suggestion = load_preview(self.preview_path).suggestions[0]
        with self.assertRaises(ValueError):
            save_approval(suggestion, "REJECTED")

    def test_skip_save_success(self) -> None:
        suggestion = load_preview(self.preview_path).suggestions[0]
        record = save_approval(suggestion, "SKIPPED")
        self.assertEqual(record.decision, "SKIPPED")

    def test_original_preview_is_not_modified(self) -> None:
        suggestion = load_preview(self.preview_path).suggestions[0]
        save_approval(suggestion, "APPROVED")
        self.assertEqual(self.preview_path.read_text(encoding="utf-8"), self.original_preview)

    def test_filters_work(self) -> None:
        preview = load_preview(self.preview_path)
        high = filter_suggestions(preview.suggestions, risk="HIGH")
        self.assertEqual(len(high), 1)
        pending = filter_suggestions(preview.suggestions, decision="PENDING")
        self.assertEqual(len(pending), 2)

    def test_approval_stats_and_rule_feedback(self) -> None:
        preview = load_preview(self.preview_path)
        save_approval(preview.suggestions[0], "APPROVED")
        save_approval(preview.suggestions[1], "REJECTED", reject_reason="数据样本不足")
        records = list(approval_store.load_approvals(preview.run_id).values())
        stats = dashboard_summary(load_preview(self.preview_path))
        feedback = rule_feedback(records)
        self.assertEqual(stats["approved"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(feedback["reject_reasons"][0][0], "数据样本不足")
        export_path = export_rejection_summary(records, "2026-07-10")
        self.assertTrue(export_path.exists())

    def test_dashboard_url_missing_does_not_error(self) -> None:
        preview = load_preview(self.preview_path)
        with patch.dict(os.environ, {}, clear=True):
            message = build_feishu_daily_summary(preview)
        self.assertIn("Dashboard URL not configured", message)

    def test_dashboard_chart_data_separates_brand_and_performance(self) -> None:
        preview = load_preview(self.preview_path)
        trend = trend_chart_data(preview, "Spend")
        performance, brand = account_comparison_chart_data(preview)
        approvals = approval_chart_data(preview)
        self.assertIn("Today", trend)
        self.assertTrue(all("ROAS" in row for row in performance))
        self.assertTrue(all("ROAS" not in row for row in brand))
        self.assertIn("Pending", approvals)

    def test_dashboard_does_not_import_meta_api_or_execute_writes(self) -> None:
        for path in [Path("dashboard/app.py"), Path("dashboard/data_loader.py"), Path("dashboard/approval_store.py")]:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("MetaMarketingAPI", text)
            self.assertNotIn("_request(", text)
            self.assertNotIn("budget-manager-apply", text)


if __name__ == "__main__":
    unittest.main()
