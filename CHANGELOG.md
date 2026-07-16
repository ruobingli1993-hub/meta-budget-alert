# Changelog

All notable project changes should be recorded here.

Format:

```text
## YYYY-MM-DD

### Added

### Changed

### Fixed
```

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
