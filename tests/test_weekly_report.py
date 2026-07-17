from __future__ import annotations

import unittest
from datetime import date

from weekly_report import CREATIVE_ACCOUNT_IDS, TRUE_GOOGLE_PURCHASE, action_value, as_date, google_channel, google_metrics, meta_account_metrics, meta_sample


class WeeklyReportTest(unittest.TestCase):
    def test_google_channel_rules(self) -> None:
        self.assertEqual(google_channel("Demand Gen", "Video_Brand_shorts"), "GOOGLE付费YOUTUBE")
        self.assertEqual(google_channel("Demand Gen", "Video prospecting"), "GOOGLE付费探索广告")
        self.assertEqual(google_channel("Shopping", "All products"), "GOOGLE付费购物广告")
        self.assertEqual(google_channel("Search", "US brand"), "GOOGLE付费品牌词")
        self.assertEqual(google_channel("Search", "US product"), "GOOGLE付费品类词")
        self.assertEqual(google_channel("Performance Max", "PMax"), "GOOGLE付费PMAX")
        self.assertEqual(google_channel("Display", "Unknown"), "未识别")

    def test_google_purchase_join_does_not_duplicate_spend(self) -> None:
        performance = [
            {"Day": date(2026, 7, 5), "Customer ID": "1", "Campaign ID": "10", "Account name": "A", "Campaign type": "Shopping", "Campaign": "Shop", "Cost": 100, "Clicks": 50, "Impr.": 1000},
            {"Day": date(2026, 7, 6), "Customer ID": "1", "Campaign ID": "10", "Account name": "A", "Campaign type": "Shopping", "Campaign": "Shop", "Cost": 20, "Clicks": 10, "Impr.": 200},
        ]
        conversions = [
            {"Day": date(2026, 7, 5), "Customer ID": "1", "Campaign ID": "10", "Conversion action": TRUE_GOOGLE_PURCHASE, "Conversions": 2, "Conv. value": 300},
            {"Day": date(2026, 7, 5), "Customer ID": "1", "Campaign ID": "10", "Conversion action": "Google Shopping App Page View (2)", "Conversions": 999, "Conv. value": 0},
        ]
        rows, unknown, unmatched = google_metrics(performance, conversions, date(2026, 7, 5), date(2026, 7, 11))
        self.assertEqual(rows[0]["Spend"], 120)
        self.assertEqual(rows[0]["Purchase"], 2)
        self.assertEqual(rows[0]["Purchase Value"], 300)
        self.assertEqual(rows[0]["Purchase ROAS"], 2.5)
        self.assertEqual(unknown, [])
        self.assertEqual(unmatched, [])

    def test_meta_funnel_uses_all_clicks_and_unknown_is_reviewed(self) -> None:
        rows = [{
            "账户名称": "A", "单周": "2026-07-05 - 2026-07-11", "受众细分": "mystery",
            "购物次数": 2, "点击量（全部）": 10, "加入购物车次数": 4, "结账发起次数": 3,
        }]
        result, reviews = meta_sample(rows, date(2026, 7, 5), date(2026, 7, 11), True)
        self.assertEqual(result[0]["Purchase CVR (All Clicks)"], 0.2)
        self.assertEqual(result[0]["ATC Rate (All Clicks)"], 0.4)
        self.assertEqual(result[0]["Checkout Rate (All Clicks)"], 0.3)
        self.assertEqual(result[0]["周报分类"], "未识别")
        self.assertEqual(len(reviews), 1)

    def test_excel_serial_date(self) -> None:
        self.assertEqual(as_date(46208), date(2026, 7, 5))

    def test_brand_and_performance_account_metrics_are_separate(self) -> None:
        rows = [
            {"账户名称": "QMDT—20240103", "已花费金额 (USD)": 100, "购物次数": 2, "购物转化价值": 300, "展示次数": 1000, "覆盖人数": 800, "点击量（全部）": 50},
            {"账户名称": "Jelenew-Brand & Lab", "已花费金额 (USD)": 50, "购物次数": 0, "购物转化价值": 0, "展示次数": 2000, "覆盖人数": 1000, "点击量（全部）": 100},
        ]
        result = {row["Account"]: row for row in meta_account_metrics(rows)}
        self.assertEqual(result["QMDT—20240103"]["ROAS"], 3)
        self.assertEqual(result["QMDT—20240103"]["Frequency"], "N/A")
        self.assertEqual(result["Jelenew-Brand & Lab"]["ROAS"], "N/A")
        self.assertEqual(result["Jelenew-Brand & Lab"]["Frequency"], 2)

    def test_creative_scope_is_only_two_performance_accounts(self) -> None:
        self.assertEqual(CREATIVE_ACCOUNT_IDS, {"750289240467952", "5600626876733411"})

    def test_meta_purchase_action_priority_does_not_double_count(self) -> None:
        rows = [
            {"action_type": "purchase", "value": "2"},
            {"action_type": "offsite_conversion.fb_pixel_purchase", "value": "99"},
            {"action_type": "omni_purchase", "value": "88"},
        ]
        self.assertEqual(action_value(rows, ("purchase", "offsite_conversion.fb_pixel_purchase", "omni_purchase")), 2)


if __name__ == "__main__":
    unittest.main()
