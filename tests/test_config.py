from __future__ import annotations

import unittest

from config import ACCOUNTS, REPORT_ACCOUNTS


class ConfigTest(unittest.TestCase):
    def test_budget_alert_and_report_accounts_are_three_unique_accounts(self) -> None:
        self.assertEqual(len(ACCOUNTS), 3)
        self.assertEqual(len(REPORT_ACCOUNTS), 3)

        budget_ids = [account.account_id for account in ACCOUNTS]
        report_ids = [account.account_id for account in REPORT_ACCOUNTS]

        self.assertEqual(len(budget_ids), len(set(budget_ids)))
        self.assertEqual(len(report_ids), len(set(report_ids)))
        self.assertIn("568835832834495", budget_ids)
        self.assertIn("568835832834495", report_ids)


if __name__ == "__main__":
    unittest.main()
