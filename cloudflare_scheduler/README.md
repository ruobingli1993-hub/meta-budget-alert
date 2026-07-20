# Cloudflare Scheduler V1

This Worker runs every 15 minutes and only dispatches existing GitHub Actions workflows. It does not read Meta data, calculate reports, call Feishu, or call any AI service.

Required setup:

1. Create a Cloudflare KV namespace and bind it as `SCHEDULER_STATE`.
2. Create a fine-grained GitHub token limited to this repository with Actions write permission only.
3. Store it as a Cloudflare secret with `wrangler secret put GITHUB_TOKEN`.
4. Deploy with `wrangler deploy`.

Do not place the GitHub token in this repository, `wrangler.toml`, Worker logs, or GitHub Secrets.

The Worker records only `run_key`, workflow name, trigger time, dispatch result, and HTTP status. GitHub Actions remains responsible for Meta reads, calculations, Feishu delivery, and delivery de-duplication.

For controlled production acceptance only, `MANUAL_TEST_JOB` may temporarily be set to `budget-alert`, `morning`, `daily-close`, or `early-pulse`. Remove it and restore the 15-minute Cron immediately after acceptance.
