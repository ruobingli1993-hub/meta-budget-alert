from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dashboard.models import ApprovalRecord, DashboardSuggestion, Decision


APPROVAL_DIR = Path("data/approvals")
REVIEW_DIR = Path("data/reviews")
RULE_FEEDBACK_DIR = Path("data/rule_feedback")
DASHBOARD_LOG = Path("logs/dashboard.log")

REJECT_REASONS = [
    "数据样本不足",
    "今天表现正在恢复",
    "账户整体表现较好，暂不降预算",
    "账户整体表现较差，暂不加预算",
    "Learning / Learning Limited",
    "预算刚刚调整过",
    "Cooldown 中",
    "Campaign 有特殊业务目标",
    "Funnel Anomaly，需先排查",
    "ABO / CBO / RTG 识别错误",
    "当前预算读取错误",
    "ROAS / Purchase Value 数据错误",
    "人工策略与系统建议不一致",
    "其他",
]


logger = logging.getLogger(__name__)


def log_dashboard(event: str, payload: dict[str, Any]) -> None:
    DASHBOARD_LOG.parent.mkdir(parents=True, exist_ok=True)
    clean = {key: value for key, value in payload.items() if "token" not in key.lower() and "webhook" not in key.lower() and "secret" not in key.lower()}
    with DASHBOARD_LOG.open("a", encoding="utf-8") as file:
        file.write(json.dumps({"created_at": datetime.now().isoformat(timespec="seconds"), "event": event, **clean}, ensure_ascii=False) + "\n")


def approval_path(run_id: str) -> Path:
    return APPROVAL_DIR / f"{run_id}.json"


def load_approvals(run_id: str) -> dict[str, ApprovalRecord]:
    path = approval_path(run_id)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {item["review_id"]: ApprovalRecord(**item) for item in payload.get("records", [])}


def save_approval(
    suggestion: DashboardSuggestion,
    decision: Decision,
    reject_reason: str = "",
    reject_note: str = "",
    reviewer: str = "Ruobing Li",
) -> ApprovalRecord:
    if decision == "REJECTED" and not reject_reason:
        raise ValueError("Reject requires a reject reason.")
    if decision not in {"APPROVED", "REJECTED", "SKIPPED"}:
        raise ValueError("Only APPROVED, REJECTED, and SKIPPED can be saved.")

    APPROVAL_DIR.mkdir(parents=True, exist_ok=True)
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_approvals(suggestion.run_id)
    record = ApprovalRecord(
        run_id=suggestion.run_id,
        review_id=suggestion.review_id,
        suggestion_type=suggestion.suggestion_type,
        account_id=suggestion.account_id,
        account_name=suggestion.account_name,
        campaign_id=suggestion.campaign_id,
        campaign_name=suggestion.campaign_name,
        adset_id=suggestion.adset_id,
        adset_name=suggestion.adset_name,
        entity_level=suggestion.entity_level,
        proposed_action=suggestion.proposed_action,
        current_budget=suggestion.current_budget,
        proposed_budget=suggestion.proposed_budget,
        change_percent=suggestion.change_percent,
        decision=decision,
        reject_reason=reject_reason if decision == "REJECTED" else "",
        reject_note=reject_note,
        reviewer=reviewer or "Ruobing Li",
        reviewed_at=datetime.now().isoformat(timespec="seconds"),
        original_metrics={
            "last_3d_spend": suggestion.last_3d_spend,
            "last_3d_purchase": suggestion.last_3d_purchase,
            "last_3d_roas": suggestion.last_3d_roas,
            "today_spend": suggestion.today_spend,
            "today_purchase": suggestion.today_purchase,
            "today_roas": suggestion.today_roas,
            "funnel_anomaly": suggestion.funnel_anomaly,
            "learning_status": suggestion.learning_status,
            "cooldown_status": suggestion.cooldown_status,
            "data_confidence": suggestion.data_confidence,
        },
        original_reason=suggestion.reason,
        confidence=suggestion.data_confidence,
        risk_level=suggestion.risk_level,
    )
    existing[record.review_id] = record
    path = approval_path(suggestion.run_id)
    payload = {"run_id": suggestion.run_id, "updated_at": datetime.now().isoformat(timespec="seconds"), "records": [asdict(item) for item in existing.values()]}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)
    log_dashboard("approval_saved", {"run_id": suggestion.run_id, "review_id": suggestion.review_id, "decision": decision, "path": str(path)})
    return record


def export_rejection_summary(records: list[ApprovalRecord], export_date: str | None = None) -> Path:
    RULE_FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
    export_date = export_date or datetime.now().date().isoformat()
    rejected = [record for record in records if record.decision == "REJECTED"]
    counts: dict[str, int] = {}
    for record in rejected:
        counts[record.reject_reason or "未填写"] = counts.get(record.reject_reason or "未填写", 0) + 1
    total = len(records)
    payload = {
        "date": export_date,
        "total_suggestions": total,
        "approved": sum(1 for record in records if record.decision == "APPROVED"),
        "rejected": len(rejected),
        "skipped": sum(1 for record in records if record.decision == "SKIPPED"),
        "reject_reasons": [
            {"reason": reason, "count": count, "share": (count / len(rejected) if rejected else 0)}
            for reason, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        ],
    }
    path = RULE_FEEDBACK_DIR / f"rejection_summary_{export_date}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_dashboard("rule_feedback_exported", {"path": str(path), "records": total})
    return path
