from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Decision = Literal["PENDING", "APPROVED", "REJECTED", "SKIPPED"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]


@dataclass(frozen=True)
class DashboardSuggestion:
    run_id: str
    review_id: str
    suggestion_type: str
    account_id: str
    account_name: str
    account_regime: str
    campaign_id: str
    campaign_name: str
    adset_id: str | None
    adset_name: str | None
    entity_level: str
    budget_model: str
    rtg: str
    current_budget: str | None
    proposed_budget: str | None
    change_percent: str
    last_3d_spend: str
    last_3d_purchase: str
    last_3d_roas: str | None
    today_spend: str
    today_purchase: str
    today_roas: str | None
    account_3d_roas: str | None
    account_today_roas: str | None
    funnel_anomaly: str
    learning_status: str
    cooldown_status: str
    data_confidence: str
    proposed_action: str
    reason: str
    optimization_hint: str
    risk_level: RiskLevel
    decision: Decision = "PENDING"
    reject_reason: str = ""
    reject_note: str = ""
    reviewer: str = ""
    reviewed_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreviewData:
    run_id: str
    created_at: str
    path: str
    suggestions: list[DashboardSuggestion]


@dataclass(frozen=True)
class ApprovalRecord:
    run_id: str
    review_id: str
    suggestion_type: str
    account_id: str
    account_name: str
    campaign_id: str
    campaign_name: str
    adset_id: str | None
    adset_name: str | None
    entity_level: str
    proposed_action: str
    current_budget: str | None
    proposed_budget: str | None
    change_percent: str
    decision: Decision
    reject_reason: str
    reject_note: str
    reviewer: str
    reviewed_at: str
    original_metrics: dict[str, Any]
    original_reason: str
    confidence: str
    risk_level: RiskLevel
