# Budget Manager Changelog

## v1.3 - 2026-07-10

### Added

- Unified Meta Data Provider shared by Morning Report and Budget Manager.
- Provider-level audit log at `logs/meta_data_provider.log`.
- Tests for Today parsing, last 3 complete days date windows, event priority/deduplication, API ERROR, EMPTY data, Account Regime ROAS protection, Learning Status cleanup, and Morning/Budget consistency.

### Fixed

- Budget Manager no longer maintains its own Meta insights request and action parsing logic.
- Account Regime blocks classification when account-level 3D ROAS or Provider status is unavailable.
- Learning Status is fully separated from API result status.

### Known Limitations

- A real Windows CMD comparison run is still required for `--morning-report` and `--budget-manager-preview`.
- Apply remains manual only and must not be run until shared Provider data is verified.

## v1.2 - 2026-07-10

### Fixed

- Changed Today insights reads to use Meta `date_preset=today` with account-timezone debug context.
- Added raw Today spend/actions/action_values and parsed purchase/ATC/checkout debug output.
- Prevented Account Regime from showing `BEAR` when account-level 3D ROAS is unavailable.
- Changed ATC Rate and Checkout Rate to use Link Clicks and display `N/A` when Link Clicks are unavailable.
- Limited Learning Status output to confirmed Meta learning states; otherwise it displays `N/A`.

### Known Limitations

- A real Windows CMD preview rerun is still required to confirm Today spend and Today ROAS from Meta.
- Apply remains manual only and must not be run until preview is approved.

## v1.1 - 2026-07-10

### Added

- Append-only audit log at `logs/budget_manager.log`.
- Per-run review report at `logs/budget_runs/<RUN_ID>.md`.
- CMD progress output for preview, apply, and rollback.
- Rule version, Python version, Git commit ID, target accounts, and config load metadata in run logs.
- Scan-result logging for account/entity metrics, ABO/CBO, RTG, budget, regime, confidence, matched rule, proposed action, and reasons.

### Fixed

- Added review artifacts so GPT or a human can audit Budget Manager runs before any write operation.

### Known Limitations

- Preview must be reviewed manually before apply.
- Apply and rollback are intentionally not automated.
- Cooldown status is recorded, but V1 cooldown enforcement is conservative and defaults to no action when uncertain.

## v1.0 - 2026-07-10

### Added

- Budget Manager Skill V1 structure.
- Preview, apply, and rollback commands.
- Config-driven budget rules.
- Preview snapshots under `logs/budget_previews`.
- Change audit log path `logs/budget_changes.jsonl`.

### Known Limitations

- No GitHub Actions integration.
- No automatic budget changes.
