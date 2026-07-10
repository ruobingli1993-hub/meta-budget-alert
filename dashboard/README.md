# Meta Automation Dashboard

Streamlit dashboard for reviewing Budget Manager Preview suggestions.

Run locally:

```bash
streamlit run dashboard/app.py
```

Local address:

```text
http://localhost:8501
```

The dashboard only reads local files:

- `logs/budget_previews/<RUN_ID>.json`
- `data/approvals/<RUN_ID>.json`
- `data/rule_feedback/*.json`

It does not call Meta API, does not send Feishu messages, and does not execute budget changes.

Home charts include:

- Overall trend chart with Today, 7D same-time average, and 30D same-time average.
- Performance account comparison for Spend and ROAS.
- Brand account comparison for Spend, CTR, and CPM.
- Review status chart for Pending, Approved, Rejected, High Risk, and Data Error.

Approval records are saved to:

```text
data/approvals/<RUN_ID>.json
```

Close the dashboard with `Ctrl+C` in the terminal where Streamlit is running.
