---
name: budget-manager
description: High-risk Meta ads budget management workflow for scanning performance accounts, producing budget-change previews, requiring human confirmation, applying changes, verifying budgets, and recording audit logs. Use for Meta budget adjustment preview/apply/rollback tasks in this project.
---

# Budget Manager

Use this skill for Meta ads budget management. Treat every budget change as high risk.

Mandatory workflow:

1. Scan Meta data.
2. Generate recommendations.
3. Send a Feishu preview.
4. Wait for human confirmation.
5. Execute only after exact confirmation.
6. Verify final budgets.
7. Record audit logs.

Default action is `NO_CHANGE`.

Never modify budgets when data is missing, inconsistent, insufficient, ambiguous, or when Meta API requests fail.

Use `config.json` as the single source of budget rules. Do not scatter thresholds or action percentages across unrelated files.

Commands:

- Preview only: `python main.py --budget-manager-preview`
- Apply preview: `python main.py --budget-manager-apply RUN_ID`
- Rollback: `python main.py --budget-manager-rollback RUN_ID`

Safety rules:

- Preview never writes Meta budgets.
- Apply requires exact `APPLY`.
- Rollback requires exact `ROLLBACK`.
- Do not accept `YES`, `Y`, or other substitutes.
- Do not process Brand accounts.
- Do not process lifetime budgets beyond preview/manual review.
- Do not print access tokens or full request URLs.
- Do not bypass cooldowns.
- Do not alter `--check-budget`, `--morning-report`, GitHub Actions, or existing reports.
