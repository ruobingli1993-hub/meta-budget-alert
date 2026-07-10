from __future__ import annotations

from dataclasses import asdict

from dashboard.models import DashboardSuggestion


def suggestion_table_rows(suggestions: list[DashboardSuggestion]) -> list[dict[str, str]]:
    return [
        {
            "Decision": item.decision,
            "Risk": item.risk_level,
            "Account": item.account_name,
            "Entity": item.entity_level,
            "Campaign": item.campaign_name,
            "Ad Set": item.adset_name or "",
            "Action": item.proposed_action,
            "Current Budget": item.current_budget or "",
            "New Budget": item.proposed_budget or "",
            "Change %": item.change_percent,
            "3D ROAS": item.last_3d_roas or "N/A",
            "Today ROAS": item.today_roas or "N/A",
            "Reason": item.reason,
        }
        for item in suggestions
    ]


def suggestion_detail(item: DashboardSuggestion) -> dict[str, object]:
    data = asdict(item)
    data.pop("raw", None)
    return data
