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
- Restored readable Chinese account names in code and README.

## Current Work

- Morning Report real Meta insights debug/failure handling fix complete.
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

- Validate the Feishu Morning Report V1 format locally.
- After report format validation, push the committed changes to GitHub.
- Later phase: implement the 18:00 complete yesterday report plus today's real-time data.

## Unresolved Issues

- The default `python`, `py`, and `python3` launchers in this Windows environment point to Windows Apps stubs and are not usable here.
- The Codex shell blocks outbound socket connections, but Windows CMD real-environment validation passed.
- Local git commit created for GitHub Actions workflow configuration.
- GitHub push failed from this shell because it could not connect to `github.com:443`.
- A local `.env` file exists. Its contents were not read or displayed during the health check.
- `__pycache__` files exist from previous local execution. They are ignored by `.gitignore`.

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
- `python3.14 main.py --morning-report` was run in Codex shell and logged all 3 accounts:
  - Processing account 1/3: QMDT—20240103 / `750289240467952`
  - Processing account 2/3: 销售三部—新主页账户 / `5600626876733411`
  - Processing account 3/3: Jelenew-Brand & Lab / `568835832834495`
- Codex shell real run still failed to connect externally, so real Meta raw insights debug rows were not available here and Feishu send did not complete.
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
