# Changelog

All notable project changes should be recorded here.

Format:

```text
## YYYY-MM-DD

### Added

### Changed

### Fixed
```

## 2026-07-17

### Added

- Added root `AGENTS.md` with project collaboration rules and advertising-operation safety boundaries.
- Added `CURRENT_TASK.md` as the single source for the next task: Budget Alert operational validation.
- Added `SCHEDULING_RELIABILITY_PLAN.md` with a 30-minute delivery target, delay detection, manual fallback, and missed-run recovery plan.
- Added `WEEKLY_REPORT_V1_REQUIREMENTS.md` as the frozen product, data-contract, priority, and acceptance source for Weekly Report V1.
- Added `weekly_report.py` for one-command generation of the three Weekly Report V1 files.
- Added Weekly Report tests for date parsing, Google channel mapping, true Purchase filtering, spend deduplication, All Clicks funnel rates, account-type metrics, and creative-account scope.

### Changed

- Rebuilt `PROJECT_DASHBOARD.md` as readable UTF-8 Chinese.
- Aligned `PROJECT_STATUS.md`, `CURRENT_TASK.md`, `PROJECT_DASHBOARD.md`, `PROJECT_CONTEXT.md`, and this changelog around no active P0 development and one next task.
- Changed the single active P0 to Weekly Report Automation V1 because a real weekly report must be delivered this week.
- Moved Budget Alert to conditional acceptance and production observation until a natural alert completes end-to-end validation.
- Recorded GitHub Actions scheduling latency as an unresolved product reliability risk.
- Frozen W27 real-date matching, BI channel deduplication, Google Purchase filtering, Meta audience mapping, and All Clicks funnel-rate definitions for Weekly Report V1.
- Clarified that Weekly Report V1 generates local files only and never sends Feishu messages.
- Limited Weekly Report V1 creative collection to the two specified Performance accounts; the Brand account remains excluded from the creative report.

### Fixed

- Removed stale Dashboard state that showed completed Feishu validation work as still in progress.
- This documentation-governance change does not modify code, GitHub Actions, advertising rules, account configuration, or budget execution logic.
- No real advertising operation or Budget Apply was executed.
- Weekly Report W27 real-data validation generated 3 account rows and 63 spending creatives from only the 2 approved Performance accounts; no Feishu message or Meta write operation was performed.

## 2026-07-14

### Added

- Initialized Project Documentation V1.
- Added `PROJECT_CONTEXT.md`.
- Added `AI_MEMORY.md`.
- Added root `CHANGELOG.md`.
- Added Documentation section to `README.md`.

### Changed

- Upgraded `PROJECT_STATUS.md` with Current Status, Completed, In Progress, Known Bugs, Next Milestone, and Recent Commits sections.

### Fixed

- No code fixes in this documentation-only change.

## 2026-07-16

### Added

- Added product-facing `PROJECT_DASHBOARD.md`.
- Added unified Budget Alert delivery logs.
- Added scheduled report delivery and account spend log fields.

### Changed

- Budget Alert state updates are now handled per account.
- Scheduled reports keep their planned Beijing slot when GitHub Actions runs late.
- Scheduled report Feishu summaries now label total spend by account count.

### Fixed

- Fixed Budget Alert cross-account state update risk.
- Fixed Budget Alert last-7-days empty insight handling so empty data does not become zero spend.
