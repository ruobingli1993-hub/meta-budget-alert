# Project Vision

Final goal:

Meta Ads Automation OS

AI analysis
-> AI suggestions
-> Human approval
-> Meta API apply
-> Feedback learning

## Project Principles

- MVP First
- Preview -> Approval -> Apply -> Rollback
- AI always suggests first
- All automation must be reversible
- Dashboard is the only operation entry point
- Feishu only sends summaries

## Current Modules

- Meta API
- Morning Report
- Scheduled Report
- Budget Alert
- Dashboard V1
- Budget Preview
- Approval
- GitHub Actions
- Streamlit

## Current Development Focus

- The single active P0 is Weekly Report Automation V1 because a real weekly report must be delivered this week.
- Budget Alert is conditionally accepted and remains under production observation until a natural real alert is delivered correctly.
- GitHub Actions scheduling latency remains an unresolved reliability risk.
- Budget Apply remains outside the current task and requires explicit approval.

## Operating Model

The project should keep high-risk actions separated from read-only reporting.
Reports and previews can run automatically, but budget changes require human review first.

The desired long-term flow is:

1. Read Meta data through shared providers.
2. Generate concise AI and rules-based observations.
3. Send only summaries to Feishu.
4. Review details and approvals in Dashboard.
5. Apply approved changes through guarded commands.
6. Verify changes and preserve audit logs.
7. Feed approval and rejection history back into future rules.
