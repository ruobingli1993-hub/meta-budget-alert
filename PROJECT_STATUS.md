# Project Status

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

## Current Work

- Unified Meta data layer refactor complete.
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

- Run `python main.py --budget-manager-preview` in Windows CMD and review the Feishu preview.
- Run `python main.py --morning-report` in Windows CMD before preview and compare Today Spend / Purchase / ROAS for the same account across both outputs.
- Review `logs/budget_manager.log` and `logs/budget_runs/<RUN_ID>.md` after preview.
- Review `logs/meta_data_provider.log` for unified request/debug data.
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
- `python3.14 -c "from config import ACCOUNTS, REPORT_ACCOUNTS; ..."` confirmed Budget Alert has 2 performance accounts and Morning Report has 3 accounts.
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
- `python3.14 -m compileall main.py skills\budget_manager`: passed.
- `python3.14 -m compileall main.py morning_report.py meta_data_provider.py skills\budget_manager tests`: passed.
- `python3.14 -m unittest tests.test_meta_data_provider`: passed.
- `python3.14 main.py --help`: passed and confirms Budget Manager preview/apply/rollback commands remain available.
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
