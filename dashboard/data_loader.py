from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from config import ACCOUNT_CONFIGS
from dashboard.approval_store import load_approvals
from dashboard.models import ApprovalRecord, DashboardSuggestion, PreviewData


PREVIEW_DIR = Path("logs/budget_previews")
WRITE_ACTIONS = {"INCREASE_25", "INCREASE_20", "INCREASE_15", "INCREASE_10", "DECREASE_25", "DECREASE_20", "DECREASE_15", "DECREASE_10"}


def latest_preview_path(preview_dir: Path = PREVIEW_DIR) -> Path | None:
    if not preview_dir.exists():
        return None
    files = sorted(preview_dir.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def load_preview(path: Path | None = None) -> PreviewData:
    path = path or latest_preview_path()
    if path is None:
        return PreviewData(run_id="", created_at="", path="", suggestions=[])
    payload = json.loads(path.read_text(encoding="utf-8"))
    run_id = str(payload.get("run_id") or path.stem)
    approvals = load_approvals(run_id)
    suggestions = [normalize_suggestion(run_id, item, approvals) for item in payload.get("recommendations", [])]
    return PreviewData(run_id=run_id, created_at=str(payload.get("created_at") or ""), path=str(path), suggestions=suggestions)


def normalize_suggestion(run_id: str, item: dict[str, Any], approvals: dict[str, ApprovalRecord] | None = None) -> DashboardSuggestion:
    review_id = make_review_id(run_id, item)
    approval = (approvals or {}).get(review_id)
    risk = risk_level(item)
    suggestion = DashboardSuggestion(
        run_id=run_id,
        review_id=review_id,
        suggestion_type="Budget Manager",
        account_id=str(item.get("account_id") or ""),
        account_name=str(item.get("account_name") or ""),
        account_regime=str(item.get("account_regime") or ""),
        campaign_id=str(item.get("campaign_id") or ""),
        campaign_name=str(item.get("campaign_name") or ""),
        adset_id=item.get("adset_id"),
        adset_name=item.get("adset_name"),
        entity_level=str(item.get("entity_level") or ""),
        budget_model=str(item.get("budget_model") or ""),
        rtg=str(item.get("rtg") or "No"),
        current_budget=item.get("current_budget"),
        proposed_budget=item.get("proposed_new_budget"),
        change_percent=str(item.get("adjustment_percentage") or "0"),
        last_3d_spend=str(item.get("last_3d_spend") or "N/A"),
        last_3d_purchase=str(item.get("last_3d_purchase") or "N/A"),
        last_3d_roas=item.get("last_3d_roas"),
        today_spend=str(item.get("today_spend") or "N/A"),
        today_purchase=str(item.get("today_purchase") or "N/A"),
        today_roas=item.get("today_roas"),
        account_3d_roas=item.get("account_3d_roas"),
        account_today_roas=item.get("account_today_roas"),
        funnel_anomaly=str(item.get("funnel_anomaly") or "No"),
        learning_status=str(item.get("learning_status") or "N/A"),
        cooldown_status=str(item.get("cooldown_status") or "N/A"),
        data_confidence=str(item.get("data_confidence") or "LOW"),
        proposed_action=str(item.get("proposed_action") or "NO_CHANGE"),
        reason=str(item.get("reason") or ""),
        optimization_hint=str(item.get("optimization_hint") or ""),
        risk_level=risk,
        raw=item,
    )
    if approval:
        suggestion = replace(
            suggestion,
            decision=approval.decision,
            reject_reason=approval.reject_reason,
            reject_note=approval.reject_note,
            reviewer=approval.reviewer,
            reviewed_at=approval.reviewed_at,
        )
    return suggestion


def make_review_id(run_id: str, item: dict[str, Any]) -> str:
    raw = "|".join(
        [
            run_id,
            str(item.get("account_id") or ""),
            str(item.get("campaign_id") or ""),
            str(item.get("adset_id") or ""),
            str(item.get("entity_level") or ""),
            str(item.get("proposed_action") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def risk_level(item: dict[str, Any]) -> str:
    pct = abs_decimal(item.get("adjustment_percentage"))
    confidence = str(item.get("data_confidence") or "").upper()
    learning = str(item.get("learning_status") or "").lower()
    cooldown = str(item.get("cooldown_status") or "").upper()
    funnel = str(item.get("funnel_anomaly") or "").lower() == "yes"
    if pct >= Decimal("25") or "learning" in learning or funnel or confidence == "LOW" or cooldown not in {"", "CLEAR", "N/A"}:
        return "HIGH"
    if pct >= Decimal("15") or confidence == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def abs_decimal(value: Any) -> Decimal:
    try:
        return abs(Decimal(str(value or "0").replace("%", "")))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def dashboard_summary(preview: PreviewData) -> dict[str, Any]:
    suggestions = preview.suggestions
    return {
        "run_id": preview.run_id,
        "total": len(suggestions),
        "pending": sum(1 for item in suggestions if item.decision == "PENDING"),
        "approved": sum(1 for item in suggestions if item.decision == "APPROVED"),
        "rejected": sum(1 for item in suggestions if item.decision == "REJECTED"),
        "skipped": sum(1 for item in suggestions if item.decision == "SKIPPED"),
        "high_risk": sum(1 for item in suggestions if item.risk_level == "HIGH"),
        "data_insufficient": sum(1 for item in suggestions if item.proposed_action == "DATA_INSUFFICIENT"),
        "data_error": sum(1 for item in suggestions if item.proposed_action == "DATA_ERROR"),
    }


def overall_summary(preview: PreviewData) -> dict[str, str]:
    per_account = account_status_rows(preview)
    spend = sum(abs_decimal(row.get("today_spend")) for row in per_account.values())
    purchase = sum(abs_decimal(row.get("today_purchase")) for row in per_account.values())
    roas_values = [abs_decimal(row.get("account_today_roas")) for row in per_account.values() if row.get("account_today_roas")]
    three_day_values = [abs_decimal(row.get("account_3d_roas")) for row in per_account.values() if row.get("account_3d_roas")]
    confidences = {item.data_confidence for item in preview.suggestions}
    return {
        "overall_status": "Needs Review" if any(row.get("account_regime") in {"BEAR", "SEVERE_BEAR", "DATA_ERROR", "DATA_INSUFFICIENT"} for row in per_account.values()) else "Stable",
        "overall_3d_roas": fmt_decimal(sum(three_day_values) / Decimal(len(three_day_values))) if three_day_values else "N/A",
        "overall_today_roas": fmt_decimal(sum(roas_values) / Decimal(len(roas_values))) if roas_values else "N/A",
        "overall_spend": fmt_decimal(spend),
        "overall_purchase": fmt_decimal(purchase),
        "overall_data_confidence": "LOW" if "LOW" in confidences else ("MEDIUM" if "MEDIUM" in confidences else "HIGH"),
    }


def account_status_rows(preview: PreviewData) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {
        account.account_id: {
            "account_id": account.account_id,
            "account_name": account.name,
            "account_type": account.account_type,
            "account_regime": "No preview data" if account.account_type == "brand" else "PENDING",
            "account_3d_roas": "N/A",
            "account_today_roas": "N/A",
            "today_spend": "N/A",
            "today_purchase": "N/A",
            "data_confidence": "N/A",
            "regime_reason": "Budget Manager Preview V1 only includes performance accounts." if account.account_type == "brand" else "",
            "ctr": "N/A",
            "frequency": "N/A",
        }
        for account in ACCOUNT_CONFIGS
    }
    for item in preview.suggestions:
        if item.account_id not in rows:
            continue
        rows[item.account_id].update(
            {
                "account_regime": item.account_regime,
                "account_3d_roas": str(item.account_3d_roas or "N/A"),
                "account_today_roas": str(item.account_today_roas or "N/A"),
                "today_spend": item.today_spend,
                "today_purchase": item.today_purchase,
                "data_confidence": item.data_confidence,
                "regime_reason": item.account_regime + ": " + item.reason,
            }
        )
    return rows


def filter_suggestions(
    suggestions: list[DashboardSuggestion],
    decision: str = "ALL",
    account_id: str = "ALL",
    action: str = "ALL",
    risk: str = "ALL",
) -> list[DashboardSuggestion]:
    rows = suggestions
    if decision != "ALL":
        rows = [item for item in rows if item.decision == decision]
    if account_id != "ALL":
        rows = [item for item in rows if item.account_id == account_id]
    if action != "ALL":
        rows = [item for item in rows if item.proposed_action == action]
    if risk != "ALL":
        rows = [item for item in rows if item.risk_level == risk]
    return rows


def rule_feedback(records: list[ApprovalRecord]) -> dict[str, Any]:
    total = len(records)
    approved = sum(1 for item in records if item.decision == "APPROVED")
    rejected = sum(1 for item in records if item.decision == "REJECTED")
    skipped = sum(1 for item in records if item.decision == "SKIPPED")
    reasons: dict[str, int] = {}
    for item in records:
        if item.decision == "REJECTED":
            reasons[item.reject_reason or "未填写"] = reasons.get(item.reject_reason or "未填写", 0) + 1
    return {
        "total": total,
        "approved": approved,
        "rejected": rejected,
        "skipped": skipped,
        "approval_rate": approved / total if total else 0,
        "reject_rate": rejected / total if total else 0,
        "reject_reasons": sorted(reasons.items(), key=lambda item: item[1], reverse=True),
    }


def automation_readiness(records: list[ApprovalRecord]) -> str:
    feedback = rule_feedback(records)
    if feedback["total"] >= 30 and feedback["reject_rate"] < 0.1:
        return "Eligible for Automation"
    return "Not Eligible Yet"


def build_feishu_daily_summary(preview: PreviewData) -> str:
    summary = overall_summary(preview)
    review = dashboard_summary(preview)
    dashboard_url = os.getenv("DASHBOARD_URL") or "Dashboard URL not configured"
    account_lines = []
    for row in account_status_rows(preview).values():
        if row["account_type"] == "brand":
            account_lines.append(f"- {row['account_name']}: {row['account_regime']} | CTR {row.get('ctr')} | Frequency {row.get('frequency')}")
        else:
            account_lines.append(f"- {row['account_name']}: {row['account_regime']} | ROAS {row['account_today_roas']}")
    return "\n".join(
        [
            "Meta Daily Summary",
            "",
            f"- Overall Account Status: {summary['overall_status']}",
            f"- Overall 3D ROAS: {summary['overall_3d_roas']}",
            f"- Overall Today ROAS: {summary['overall_today_roas']}",
            f"- Overall Spend: {summary['overall_spend']}",
            f"- Overall Purchase: {summary['overall_purchase']}",
            "",
            "Account Status:",
            *account_lines,
            "",
            "Review Summary:",
            f"- Suggestions: {review['total']}",
            f"- Pending: {review['pending']}",
            f"- Approved: {review['approved']}",
            f"- Rejected: {review['rejected']}",
            f"- High Risk: {review['high_risk']}",
            "",
            "View More:",
            dashboard_url,
        ]
    )


def fmt_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))
