from __future__ import annotations

import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


WRITE_ACTIONS = {
    "INCREASE_25",
    "INCREASE_20",
    "INCREASE_15",
    "INCREASE_10",
    "DECREASE_25",
    "DECREASE_20",
    "DECREASE_15",
    "DECREASE_10",
}
BLOCKED_ACTIONS = {"DATA_INSUFFICIENT", "DATA_ERROR", "MANUAL_REVIEW", "COOLDOWN"}


def git_commit_id() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unavailable"


def append_log(config: dict[str, Any], event: dict[str, Any]) -> None:
    path = Path(config["manager_log_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_event = redact(event)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(clean_event, ensure_ascii=False) + "\n")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("[REDACTED]" if key.lower() in {"access_token", "authorization", "meta_access_token", "feishu_webhook_url"} else redact(item))
            for key, item in value.items()
            if "url" not in key.lower()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def run_base(run_id: str, mode: str, start_time: str, config: dict[str, Any], target_accounts: list[str]) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "mode": mode,
        "start_time": start_time,
        "rule_version": config.get("rule_version", "unknown"),
        "python_version": platform.python_version(),
        "git_commit_id": git_commit_id(),
        "target_accounts": target_accounts,
        "config_load_result": "SUCCESS",
    }


def overall_status(recommendations: list[dict[str, Any]], failed: bool = False) -> str:
    if failed:
        return "FAILED"
    if not recommendations:
        return "FAILED"
    error_count = sum(1 for item in recommendations if item.get("proposed_action") == "DATA_ERROR")
    if error_count == len(recommendations):
        return "FAILED"
    if error_count:
        return "PARTIAL"
    return "SUCCESS"


def save_run_report(
    config: dict[str, Any],
    run_id: str,
    mode: str,
    start_time: str,
    end_time: str,
    status: str,
    recommendations: list[dict[str, Any]],
    errors: list[str] | None = None,
) -> Path:
    directory = Path(config["run_report_dir"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.md"
    path.write_text(
        build_report(run_id, mode, start_time, end_time, status, recommendations, errors or []),
        encoding="utf-8",
    )
    return path


def build_report(
    run_id: str,
    mode: str,
    start_time: str,
    end_time: str,
    status: str,
    recommendations: list[dict[str, Any]],
    errors: list[str],
) -> str:
    proposed = [item for item in recommendations if item.get("proposed_action") in WRITE_ACTIONS]
    blocked = [item for item in recommendations if item.get("proposed_action") not in WRITE_ACTIONS]
    lines = [
        "# Budget Manager Run Report",
        "",
        "## Run Information",
        f"- Run ID: {run_id}",
        f"- Mode: {mode}",
        f"- Start Time: {start_time}",
        f"- End Time: {end_time}",
        f"- Overall Status: {status}",
        "",
        "## Account Regime Summary",
    ]
    seen_accounts = set()
    for item in recommendations:
        key = item.get("account_id")
        if key in seen_accounts:
            continue
        seen_accounts.add(key)
        lines.extend(
            [
                f"- Account Name: {item.get('account_name')}",
                f"  Account ID: {item.get('account_id')}",
                f"  Regime: {item.get('account_regime')}",
                f"  3D ROAS: {item.get('account_3d_roas')}",
                f"  Today ROAS: {item.get('account_today_roas')}",
                f"  Data Confidence: {item.get('data_confidence')}",
                f"  Regime Reason: {item.get('account_regime_reason') or item.get('reason')}",
            ]
        )

    lines.extend(["", "## Proposed Changes"])
    if not proposed:
        lines.append("- None")
    for item in proposed:
        lines.extend(
            [
                f"- Entity Level: {item.get('entity_level')}",
                f"  Campaign / Ad Set Name: {item.get('campaign_name')} / {item.get('adset_name')}",
                f"  ID: {item.get('campaign_id')} / {item.get('adset_id')}",
                f"  Current Budget: {item.get('current_budget')} {item.get('currency')}",
                f"  New Budget: {item.get('proposed_new_budget')} {item.get('currency')}",
                f"  Change %: {item.get('adjustment_percentage')}",
                f"  Rule: {item.get('matched_rule')}",
                f"  Reason: {item.get('reason')}",
            ]
        )

    lines.extend(["", "## No Change / Blocked"])
    if not blocked:
        lines.append("- None")
    for item in blocked:
        lines.append(
            f"- {item.get('proposed_action')}: {item.get('account_name')} | {item.get('entity_level')} | {item.get('campaign_name')} | {item.get('adset_name')} | {item.get('reason')}"
        )

    lines.extend(["", "## Errors"])
    data_errors = [item for item in recommendations if item.get("proposed_action") == "DATA_ERROR"]
    if not errors and not data_errors:
        lines.append("- None")
    for error in errors:
        lines.append(f"- {error}")
    for item in data_errors:
        lines.append(f"- {item.get('account_name')} / {item.get('campaign_name')} / {item.get('adset_name')}: {item.get('reason')}")

    lines.extend(["", "## Debug Details"])
    if not recommendations:
        lines.append("- None")
    for item in recommendations:
        lines.extend(
            [
                f"- Account: {item.get('account_name')} / {item.get('account_id')}",
                f"  Entity: {item.get('entity_level')} | {item.get('campaign_name')} | {item.get('adset_name')}",
                f"  Account Timezone: {item.get('account_timezone')}",
                f"  Today Request: date_preset={item.get('today_date_preset') or 'N/A'}, since={item.get('today_request_since')}, until={item.get('today_request_until')}",
                f"  Raw Insights Has Data: {item.get('today_raw_has_data')}",
                f"  Raw Today Spend: {item.get('today_raw_spend')}",
                f"  Raw Today Actions: {json.dumps(item.get('today_raw_actions') or [], ensure_ascii=False)}",
                f"  Raw Today Action Values: {json.dumps(item.get('today_raw_action_values') or [], ensure_ascii=False)}",
                f"  Parsed Today Purchase / ATC / Checkout: {item.get('parsed_today_purchase')} / {item.get('parsed_today_atc')} / {item.get('parsed_today_checkout')}",
                f"  Parsed Today Link Clicks: {item.get('parsed_today_link_clicks')}",
                f"  Regime Calculation Inputs: {json.dumps(item.get('regime_calculation_inputs') or {}, ensure_ascii=False)}",
            ]
        )

    summary = summarize(recommendations)
    lines.extend(
        [
            "",
            "## Summary",
            f"- Scanned Campaigns: {summary['campaigns']}",
            f"- Scanned Ad Sets: {summary['adsets']}",
            f"- Increase Count: {summary['increase']}",
            f"- Decrease Count: {summary['decrease']}",
            f"- No Change Count: {summary['no_change']}",
            f"- Blocked Count: {summary['blocked']}",
            f"- Error Count: {summary['errors']}",
            "",
        ]
    )
    return "\n".join(lines)


def summarize(recommendations: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "campaigns": sum(1 for item in recommendations if item.get("entity_level") == "Campaign"),
        "adsets": sum(1 for item in recommendations if item.get("entity_level") == "Ad Set"),
        "increase": sum(1 for item in recommendations if str(item.get("proposed_action", "")).startswith("INCREASE")),
        "decrease": sum(1 for item in recommendations if str(item.get("proposed_action", "")).startswith("DECREASE")),
        "no_change": sum(1 for item in recommendations if item.get("proposed_action") == "NO_CHANGE"),
        "blocked": sum(1 for item in recommendations if item.get("proposed_action") in BLOCKED_ACTIONS),
        "errors": sum(1 for item in recommendations if item.get("proposed_action") == "DATA_ERROR"),
    }
