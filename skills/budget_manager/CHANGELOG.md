# Budget Manager Changelog

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
