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
- Restored readable Chinese account names in code and README.

## Current Work

- Formal budget check command implementation complete.
- No active feature development.
- GitHub Actions setup is intentionally paused per user instruction.

## Environment

- Date checked: 2026-07-07 Asia/Shanghai.
- Windows CMD is available and was used for real-environment validation.
- Python 3.14.6 is available and working.
- Python dependencies: `requests` and `python-dotenv` are importable.
- Feishu webhook real test passed.
- Meta API real read passed.
- Git: not installed or not available in this shell.
- `.env`: exists.
- `.env` required variables:
  - `META_ACCESS_TOKEN`: set.
  - `FEISHU_WEBHOOK_URL`: set.
- Secret values were not printed.

## Suggested Next Steps

- Run `python main.py --check-budget` from Windows CMD to perform the first real budget check.
- If no account is below threshold, confirm the terminal prints only `No alert needed`.
- If an account is below threshold, confirm Feishu receives one formal alert for that account.
- Run `python main.py --check-budget` a second time while still below threshold to confirm `state.json` prevents duplicate alerts.
- Install Git if source-control checks are needed locally.
- Keep GitHub Actions paused until explicitly requested.

## Unresolved Issues

- The default `python`, `py`, and `python3` launchers in this Windows environment point to Windows Apps stubs and are not usable here.
- `git` is not available in this shell, so git status checks could not be performed.
- The Codex shell blocks outbound socket connections, but Windows CMD real-environment validation passed.
- A local `.env` file exists. Its contents were not read or displayed during the health check.
- `__pycache__` files exist from previous local execution. They are ignored by `.gitignore`.

## Latest Test Results

Last checked: 2026-07-07 Asia/Shanghai

- `python3.14 --version`: passed, Python 3.14.6.
- `.env` presence check: passed.
- Required `.env` variable presence check: passed.
- `python3.14 -c "import requests, dotenv"`: passed.
- `python3.14 -m compileall .`: passed.
- `python3.14 main.py --help`: passed and confirms `--meta-test` and `--check-budget` are available.
- `python main.py --notify-test`: passed in Windows CMD.
- `python main.py --meta-test`: passed in Windows CMD.
- QMDT—20240103 returned balance, last 7 days spend, and average daily spend.
- 销售三部—新主页账户 returned balance, last 7 days spend, and average daily spend.
- `state.json` remained unchanged during local compile/help verification.
- Feishu webhook URL was not printed in logs.
