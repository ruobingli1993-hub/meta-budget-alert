# Project Status

## Current Status

- Project Documentation V1 is initialized.
- Budget Alert monitors three accounts, including Jelenew-Brand & Lab.
- Budget Alert Debug is the current P0 operational focus.
- Dashboard V1 is available as the detail and approval workspace.
- Feishu is kept as a summary-only notification channel.
- No budget apply has been executed.

## Completed

- Meta API integration
- Morning Report
- Scheduled Report
- Budget Alert
- Budget Alert Debug
- Dashboard V1
- Budget Preview
- Approval records
- GitHub Actions budget check
- Streamlit dashboard foundation
- Shared Meta Data Provider
- Brand account added to Budget Alert
- Project Documentation V1

## In Progress

- P0 Budget Alert Debug validation and operational hardening
- P1 Dashboard V2 planning

## Known Bugs

- Windows terminal output can show mojibake for Chinese text in some shell contexts.
- The default `python`, `py`, and `python3` launchers in this environment point to Windows Apps stubs.
- Streamlit is listed in `requirements.txt`, but it is not installed in the current Codex shell environment.
- Local `state.json` changes after real checks should not be committed unless intentionally requested.

## Next Milestone

- Finish Budget Alert operational validation.
- Then move to Dashboard V2.
- Later add Weekly Report.
- Keep Budget Apply behind preview, approval, explicit confirmation, verification, and rollback.

## Recent Commits

- `61faf04` Add Brand account to budget alerts
- `f82b646` Add budget alert debug mode
- `9b4f08a` Simplify scheduled reports and add dashboard charts
- `0bdda60` Add scheduled Meta reports
- `e41128d` Add dashboard approval center

## Maintenance Rule

After each completed development task, bug fix, or new feature, update this file with:

- Completed features
- Current work
- Suggested next steps
- Unresolved issues
- Latest test results

## Completed Features

- Created the Meta ad account budget alert Python project.
- Added two monitored accounts:
  - QMDT—20240103 / `750289240467952`
  - 销售三部—新主页账户 / `5600626876733411`
- Implemented Meta Marketing API budget snapshot fetching.
- Implemented Feishu webhook notification sending.
- Implemented alert de-duplication with local `state.json`.
- Added environment-variable based configuration for `META_ACCESS_TOKEN` and `FEISHU_WEBHOOK_URL`.
- Added dry-run mode via `--dry-run` or `DRY_RUN=true`.
- Ensured dry-run mode does not call Meta API, does not send Feishu messages, and does not modify `state.json`.
- Added Feishu connectivity test mode via `--notify-test`.
- Added Meta read-only verification mode via `--meta-test`.
- Added formal budget check mode via `--check-budget`.
- Configured GitHub Actions daily budget check at Beijing time 09:00.
- GitHub Actions budget check workflow deployed.
- Manual GitHub Actions run passed.
- Implemented Morning Report V1 with overall summary, account summaries, campaign ranking, health/anomaly summary, and today's observations.
- Added `--morning-report` command.
- Centralized account configuration in `config.py`.
- Added Jelenew-Brand & Lab as the third Morning Report account.
- Fixed Morning Report account traversal so all three configured accounts are processed.
- Added per-account failure reporting in Morning Report output.
- Added Morning Report terminal progress logs for configured account count and per-account processing.
- Simplified Morning Report V1 to Overall Total Summary, Account Performance Summary, and Campaign Ranking only.
- Changed Morning Report balance source to account spend limit remaining balance.
- Changed Morning Report CTR display to plain percentages without leading plus signs.
- Changed Morning Report Campaign Ranking to Top 1 Campaign and Bottom 1 Campaign.
- Added Morning Report Meta insights debug logs for raw spend, impressions, clicks, purchase, and purchase value.
- Changed Morning Report insights parsing so missing required insight fields become account-level data fetch failures instead of silently becoming zero.
- Added all-accounts-failed Morning Report failure notice instead of sending a normal zero-metric report.
- Added explicit Morning Report send result messages for normal reports and failure notices.
- Added Budget Manager Skill V1 files under `skills/budget_manager`.
- Added guarded Budget Manager commands: `--budget-manager-preview`, `--budget-manager-apply RUN_ID`, and `--budget-manager-rollback RUN_ID`.
- Added Budget Manager preview snapshot storage under `logs/budget_previews`.
- Added Budget Manager audit log path `logs/budget_changes.jsonl`.
- Added Budget Manager append-only run log at `logs/budget_manager.log`.
- Added Budget Manager per-run report at `logs/budget_runs/<RUN_ID>.md`.
- Added Budget Manager CHANGELOG at `skills/budget_manager/CHANGELOG.md`.
- Added CMD progress output for Budget Manager preview/apply/rollback.
- Restored readable Chinese account names in code and README.
- Fixed Budget Manager Preview Today insights debugging:
  - Today reads now use Meta `date_preset=today` and log the ad account timezone plus expected since/until dates.
  - Preview logs now include raw Today spend, actions, action_values, and parsed purchase / ATC / checkout.
  - Link Clicks are used as the ATC / Checkout rate denominator; rates display `N/A` when Link Clicks are unavailable.
  - Account Regime no longer reports `BEAR` when account-level 3D ROAS is unavailable.
  - Learning Status now displays only confirmed Meta learning states; otherwise it displays `N/A`.
  - Single-run reports now include a Debug Details section for GPT review.
- Added a unified Meta Data Provider in `meta_data_provider.py`.
- Refactored Morning Report and Budget Manager Preview to consume the same Meta Data Provider for insights parsing and account timezone date windows.
- Added Provider log output at `logs/meta_data_provider.log`.
- Added provider-level tests for Today parsing, last 3 complete days, QMDT-style ROAS parsing, event deduplication, API ERROR, EMPTY data, Account Regime ROAS protection, Learning Status cleanup, and Morning/Budget data consistency.
- Added Streamlit Dashboard V1 under `dashboard/`.
- Added local approval records at `data/approvals/<RUN_ID>.json`.
- Added Rule Feedback export at `data/rule_feedback/rejection_summary_<date>.json`.
- Added Dashboard runtime log at `logs/dashboard.log`.
- Added concise Feishu Budget Manager Preview summary with `DASHBOARD_URL` support.
- Added Dashboard tests for preview loading, summaries, account status, Approve, Reject, Skip, original preview protection, filters, approval stats, Rule Feedback, missing `DASHBOARD_URL`, no Meta API calls, and no real write execution.
- Added unified scheduled report command: `python main.py --scheduled-report morning|daily-close|early-pulse`.
- Added three concise scheduled Meta reports:
  - 09:00 Beijing Morning Realtime with same-time-window comparison.
  - 15:30 Beijing Daily Close with previous complete account day.
  - 18:00 Beijing Early Pulse with early same-time-window comparison.
- Added scheduled report logging at `logs/scheduled_reports.log`.
- Added independent GitHub Actions workflow at `.github/workflows/scheduled_reports.yml`.
- Added scheduled report tests for time windows, America/Phoenix date boundaries, Brand health rules, all-account vs performance ROAS, API failure protection, Dashboard URL fallback, cron values, and manual workflow dispatch.
- Simplified scheduled Feishu reports to concise summary lines only.
- Fixed scheduled report status logic so LOW confidence plus unavailable Performance ROAS becomes `DATA_INSUFFICIENT`.
- Fixed missing Purchase Value handling so Revenue / ROAS display `N/A` instead of `0.00`.
- Fixed Brand Account health logic so missing Reach / Frequency becomes `DATA_INSUFFICIENT`.
- Added Review RUN_ID and generated time to scheduled report Review Summary.
- Added `--as-of` for local scheduled-report time simulation.
- Added Dashboard home charts for trend, account comparison, and review status.
- Added read-only Budget Alert Debug mode via `--check-budget-debug`.
- Updated Budget Alert balance calculation to use only `account_spend_limit - amount_spent`.
- Updated Budget Alert spend baseline to use the last 7 complete account-timezone days.
- Updated Budget Alert de-duplication to allow a repeat alert after 24 hours while still clearing state after recovery.
- Added Budget Alert Debug log at `logs/budget_alert_debug.log`.
- Fixed Meta spend-cap field mapping: API now requests `spend_cap` and maps it to the internal `account_spend_limit` field.
- Added Budget Alert output for `account_status` and explicit `spend_cap` / `remaining_balance` debug fields.
- Added Jelenew-Brand & Lab / `568835832834495` to Budget Alert monitoring.
- Confirmed Budget Alert and Morning Report both contain the same three unique configured accounts.

## Current Work

- Project Documentation V1 initialized.
- No active feature development.

## Environment

- Date checked: 2026-07-07 Asia/Shanghai.
- Windows CMD is available and was used for real-environment validation.
- Python 3.14.6 is available and working.
- Python dependencies: `requests` and `python-dotenv` are importable.
- Feishu webhook real test passed.
- Meta API real read passed.
- GitHub Secrets are configured by the user:
  - `META_ACCESS_TOKEN`
  - `FEISHU_WEBHOOK_URL`
- Git: available at `C:\Program Files\Git\cmd\git.exe`.
- `.env`: exists.
- `.env` required variables:
  - `META_ACCESS_TOKEN`: set.
  - `FEISHU_WEBHOOK_URL`: set.
- Secret values were not printed.

## Suggested Next Steps

- Run `python main.py --check-budget-debug` in Windows CMD to inspect why a low remaining spend limit may not send Feishu.
- Review `logs/budget_alert_debug.log` after the debug run.
- Run `python main.py --budget-manager-preview` in Windows CMD and review the Feishu preview.
- Run `python main.py --morning-report` in Windows CMD before preview and compare Today Spend / Purchase / ROAS for the same account across both outputs.
- Start Dashboard locally with `streamlit run dashboard/app.py`.
- Review and record Budget Manager Preview decisions in Dashboard before any future apply step.
- Manually test scheduled reports in Windows CMD:
  - `python main.py --scheduled-report morning`
  - `python main.py --scheduled-report daily-close`
  - `python main.py --scheduled-report early-pulse`
- Test report time windows locally with:
  - `python main.py --scheduled-report morning --as-of "2026-07-10T18:00:00-07:00"`
  - `python main.py --scheduled-report early-pulse --as-of "2026-07-10T03:00:00-07:00"`
- Review `logs/budget_manager.log` and `logs/budget_runs/<RUN_ID>.md` after preview.
- Review `logs/meta_data_provider.log` for unified request/debug data.
- Review `logs/scheduled_reports.log` after scheduled report tests.
- Do not run `--budget-manager-apply` until preview is confirmed.
- After report format validation, push the committed changes to GitHub.
- Later phase: implement the 18:00 complete yesterday report plus today's real-time data.

## Unresolved Issues

- The default `python`, `py`, and `python3` launchers in this Windows environment point to Windows Apps stubs and are not usable here.
- The Codex shell blocks outbound socket connections, but Windows CMD real-environment validation passed.
- Local git commit created for GitHub Actions workflow configuration.
- GitHub push failed from this shell because it could not connect to `github.com:443`.
- A local `.env` file exists. Its contents were not read or displayed during the health check.
- `__pycache__` files exist from previous local execution. They are ignored by `.gitignore`.
- Budget Manager Preview and Morning Report need one real Windows CMD comparison run to confirm Today Spend / Purchase / ROAS now match through the shared Provider.
- No real budget apply has been executed.
- Dashboard V1 is local-only and has not been publicly deployed.
- Streamlit is added to `requirements.txt`; the Codex shell does not currently have Streamlit installed, so the Dashboard server was not started here.
- Scheduled report commands were compile/unit tested locally but not run against real Meta/Feishu from Codex shell.
- Budget Alert Debug was real-read tested against Meta after switching from `account_spend_limit` to `spend_cap`.

## Latest Test Results

Last checked: 2026-07-07 Asia/Shanghai

- `python3.14 --version`: passed, Python 3.14.6.
- `.env` presence check: passed.
- Required `.env` variable presence check: passed.
- `python3.14 -c "import requests, dotenv"`: passed.
- `python3.14 -m compileall .`: passed.
- `python3.14 main.py --help`: passed and confirms `--meta-test`, `--check-budget`, and `--morning-report` are available.
- Morning Report fake-data build test: passed.
- Morning Report output structure includes all five required sections.
- Campaign action validation confirmed V1 does not output Pause, Scale, or Increase Budget.
- `python3.14 -c "from config import ACCOUNTS, REPORT_ACCOUNTS; ..."` confirmed Budget Alert has 3 accounts and Morning Report has 3 accounts, with no duplicate account IDs.
- Morning Report all-three-accounts fake-data test: passed.
- Morning Report failed-account visibility test: passed.
- Morning Report simplified fake-data test: passed.
- Simplified report no longer includes Health & Anomaly Summary, Today's Observation, or campaign action judgments.
- Correct Balance displays account spend limit remaining balance when available, otherwise `Balance source unavailable`.
- CTR fields now render as plain percentages, for example `2.00%`.
- Campaign Ranking now renders Top 1 Campaign and Bottom 1 Campaign for each account.
- Morning Report real insights mapping fake-data test: passed.
- Morning Report missing spend failure test: passed.
- Morning Report all-accounts-failed notice test: passed.
- Morning Report partial failure test: passed.
- Budget Manager command wiring compile/help validation: passed.
- Budget Manager config load validation: passed.
- GitHub Actions workflow unchanged for Budget Manager work.
- Budget Manager run-log/report implementation validation: passed.
- Budget Manager Preview parser/regime fake-data test: passed.
- Unified Meta Data Provider tests: passed, 9 tests.
- Dashboard tests: passed, 10 tests.
- Scheduled report tests: passed, 8 tests.
- Scheduled report simplification tests: passed.
- Dashboard chart data tests: passed.
- `python3.14 -m compileall main.py skills\budget_manager`: passed.
- `python3.14 -m compileall main.py morning_report.py meta_data_provider.py skills\budget_manager tests`: passed.
- `python3.14 -m compileall main.py scheduled_reports.py meta_data_provider.py tests`: passed.
- `python3.14 -m unittest tests.test_meta_data_provider`: passed.
- `python3.14 -m unittest tests.test_dashboard tests.test_meta_data_provider`: passed, 19 tests.
- `python3.14 -m unittest tests.test_scheduled_reports tests.test_dashboard tests.test_meta_data_provider`: passed, 27 tests.
- `python3.14 -m unittest tests.test_scheduled_reports tests.test_dashboard tests.test_meta_data_provider`: passed, 32 tests.
- `python3.14 main.py --help`: passed and confirms Budget Manager preview/apply/rollback commands remain available.
- `python3.14 -m compileall main.py meta_api.py notifier.py tests`: passed.
- `python3.14 -m unittest tests.test_budget_alert`: passed, 6 tests.
- `python3.14 main.py --help`: passed and confirms `--check-budget-debug` is available.
- Budget Alert Debug validation confirms no Feishu send and no `state.json` write path in debug mode.
- Budget Alert de-duplication unit tests confirm duplicate alerts are blocked inside 24 hours, repeat alerts are allowed after 24 hours, and recovery clears `last_alert_sent_at`.
- `python3.14 -m compileall .`: passed.
- `python3.14 -m unittest discover -s tests`: passed, 38 tests.
- `python3.14 main.py --check-budget-debug`: passed with real Meta reads.
- QMDT—20240103 real Debug result: `spend_cap` `$1291000.01`, `amount_spent` `$1225998.44`, `remaining_balance` `$65001.57`, currency `USD`, account status `1`.
- 销售三部—新主页账户 real Debug result: `spend_cap` `$140031.00`, `amount_spent` `$137327.38`, `remaining_balance` `$2703.62`, currency `USD`, account status `1`.
- `python3.14 main.py --check-budget`: passed with real Meta reads and updated `state.json`; no Feishu alert was sent because both accounts were above the 3-day threshold.
- `python3.14 -m compileall main.py config.py meta_api.py notifier.py tests`: passed.
- `python3.14 -m unittest discover -s tests`: passed, 39 tests.
- `python3.14 -c "from config import ACCOUNTS, REPORT_ACCOUNTS; ..."` confirmed Budget Alert has 3 accounts and Morning Report has 3 accounts, with no duplicate account IDs.
- `python3.14 main.py --check-budget-debug`: passed with real Meta reads for all 3 Budget Alert accounts and did not modify `state.json`.
- Jelenew-Brand & Lab real Debug result: `spend_cap` `$131900.01`, `amount_spent` `$116385.34`, `remaining_balance` `$15514.67`, average daily spend `$79.69`, 3-day threshold `$239.08`, currency `USD`, account status `1`, final trigger `FALSE`.
- `python3.14 main.py --check-budget`: passed with real Meta reads for all 3 Budget Alert accounts; no Feishu alert was sent because all three accounts were above the 3-day threshold.
- `python3.14 -c "import streamlit"`: failed in Codex shell because Streamlit is not installed in this environment; install with `pip install -r requirements.txt` in Windows CMD.
- `git diff --check`: passed.
- Real `python main.py --budget-manager-preview` was not run by Codex for this fix because it sends a Feishu preview; next validation should be run by the user in Windows CMD.
- `python3.14 main.py --morning-report` was run in Codex shell and logged all 3 accounts:
  - Processing account 1/3: QMDT—20240103 / `750289240467952`
  - Processing account 2/3: 销售三部—新主页账户 / `5600626876733411`
  - Processing account 3/3: Jelenew-Brand & Lab / `568835832834495`
- Codex shell real run logged per-account Meta API failure details with HTTP status code, Meta error code, and Meta error message.
- Codex shell real run still failed to connect externally, so Feishu send did not complete here.
- Local git commit created: `Add Morning Report V1`.
- Workflow updated to run `python main.py --check-budget` daily at cron `0 1 * * *`.
- Local git commit created: `Configure daily budget check workflow`.
- `git push origin main`: failed from this shell because GitHub was unreachable on port 443.
- `git push origin main`: passed in Windows CMD.
- GitHub Actions `workflow_dispatch` manual run: passed.
- `check-budget` job completed successfully.
- `python main.py --notify-test`: passed in Windows CMD.
- `python main.py --meta-test`: passed in Windows CMD.
- QMDT—20240103 returned balance, last 7 days spend, and average daily spend.
- 销售三部—新主页账户 returned balance, last 7 days spend, and average daily spend.
- `state.json` remained unchanged during local compile/help verification.
- Feishu webhook URL was not printed in logs.
- Project Documentation V1 documentation-only update completed; no Python, Dashboard, Workflow, Budget Rule, or apply command was changed or run.
