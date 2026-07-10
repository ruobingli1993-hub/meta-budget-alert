from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from config import ACCOUNT_CONFIGS
from feishu import FeishuWebhookClient
from meta_api import MetaMarketingAPI
from skills.budget_manager import analyzer, rules


def apply(run_id: str) -> int:
    config = rules.load_config()
    snapshot = load_preview(run_id, config)
    executable = [row for row in snapshot["recommendations"] if row["proposed_action"] not in rules.NO_WRITE_ACTIONS and row["proposed_new_budget"]]
    if not executable:
        print("No executable budget changes in preview.")
        return 0

    api = MetaMarketingAPI()
    validate_preview_still_current(api, executable, config)
    print(analyzer.format_preview({"run_id": run_id, "recommendations": executable}))
    if input("Type APPLY to execute: ").strip() != "APPLY":
        print("Apply cancelled.")
        return 1

    backup = create_backup(api, run_id, executable, config)
    results = []
    for row in executable:
        entity_id = row["adset_id"] if row["entity_level"] == "Ad Set" else row["campaign_id"]
        if not entity_id:
            results.append({"row": row, "status": "SKIPPED", "reason": "Missing entity id"})
            continue
        before = read_budget(api, entity_id, row["currency"])
        target = Decimal(str(row["proposed_new_budget"]))
        write_budget(api, entity_id, row["currency"], target)
        after = read_budget(api, entity_id, row["currency"])
        result = {"row": row, "status": "DONE", "before": before, "target": str(target), "after": after}
        results.append(result)
        append_change_log(run_id, result, config)

    message = format_apply_result(run_id, results, backup)
    print(message)
    FeishuWebhookClient().send_text(message)
    return 0


def rollback(run_id: str) -> int:
    config = rules.load_config()
    backup_path = Path(config["latest_budget_backup_path"])
    if not backup_path.exists():
        print("No latest budget backup found.")
        return 1
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    if backup.get("run_id") != run_id:
        print("Backup RUN_ID does not match requested rollback RUN_ID.")
        return 1
    if input("Type ROLLBACK to execute: ").strip() != "ROLLBACK":
        print("Rollback cancelled.")
        return 1

    api = MetaMarketingAPI()
    results = []
    for row in backup["budgets"]:
        write_budget(api, row["entity_id"], row["currency"], Decimal(str(row["budget"])))
        final = read_budget(api, row["entity_id"], row["currency"])
        results.append({"entity_id": row["entity_id"], "target": row["budget"], "final": final})
    message = "Budget rollback completed\nRUN_ID: " + run_id + "\n" + json.dumps(results, ensure_ascii=False, indent=2)
    print(message)
    FeishuWebhookClient().send_text(message)
    return 0


def load_preview(run_id: str, config: dict[str, Any]) -> dict[str, Any]:
    path = Path(config["preview_log_dir"]) / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Preview snapshot not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def create_backup(api: MetaMarketingAPI, run_id: str, rows: list[dict[str, Any]], config: dict[str, Any]) -> dict[str, Any]:
    budgets = []
    for row in rows:
        entity_id = row["adset_id"] if row["entity_level"] == "Ad Set" else row["campaign_id"]
        budgets.append({"entity_id": entity_id, "budget": read_budget(api, entity_id, row["currency"]), "currency": row["currency"]})
    backup = {"run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"), "budgets": budgets}
    Path(config["latest_budget_backup_path"]).parent.mkdir(parents=True, exist_ok=True)
    Path(config["latest_budget_backup_path"]).write_text(json.dumps(backup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return backup


def read_budget(api: MetaMarketingAPI, entity_id: str, currency: str) -> str:
    payload = api._request("GET", f"{api.base_url}/{entity_id}", params={"fields": "daily_budget", "access_token": api.access_token})
    budget = analyzer.parse_budget(payload.get("daily_budget"), currency)
    return str(budget or "0")


def write_budget(api: MetaMarketingAPI, entity_id: str, currency: str, budget: Decimal) -> None:
    multiplier = Decimal("1") if currency.upper() in {"BIF", "CLP", "DJF", "GNF", "JPY", "KMF", "KRW", "MGA", "PYG", "RWF", "UGX", "VND", "VUV", "XAF", "XOF", "XPF"} else Decimal("100")
    minor = int((budget * multiplier).to_integral_value())
    api._request("POST", f"{api.base_url}/{entity_id}", params={"daily_budget": minor, "access_token": api.access_token})


def append_change_log(run_id: str, result: dict[str, Any], config: dict[str, Any]) -> None:
    path = Path(config["change_log_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"run_id": run_id, "created_at": datetime.now().isoformat(timespec="seconds"), **result}
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def format_apply_result(run_id: str, results: list[dict[str, Any]], backup: dict[str, Any]) -> str:
    return "Budget Manager Apply Result\nRUN_ID: " + run_id + "\n" + json.dumps({"results": results, "backup": backup}, ensure_ascii=False, indent=2)


def validate_preview_still_current(api: MetaMarketingAPI, rows: list[dict[str, Any]], config: dict[str, Any]) -> None:
    fresh_rows: list[dict[str, Any]] = []
    for account in ACCOUNT_CONFIGS:
        if account.account_type != config["performance_account_type"]:
            continue
        fresh_rows.extend([item.__dict__ for item in analyzer.analyze_account(api, account, config)])

    fresh_by_key = {preview_key(row): row for row in fresh_rows}
    core_fields = [
        "current_budget",
        "last_3d_spend",
        "last_3d_purchase",
        "last_3d_purchase_value",
        "last_3d_roas",
        "today_spend",
        "today_purchase",
        "today_purchase_value",
        "today_roas",
        "proposed_action",
        "proposed_new_budget",
    ]
    for row in rows:
        fresh = fresh_by_key.get(preview_key(row))
        if not fresh:
            raise RuntimeError(f"Preview entity no longer found: {preview_key(row)}")
        for field in core_fields:
            if str(row.get(field)) != str(fresh.get(field)):
                raise RuntimeError(f"Preview data changed for {preview_key(row)} field {field}. Stop apply.")


def preview_key(row: dict[str, Any]) -> tuple[str, str | None, str | None]:
    return (str(row.get("entity_level")), row.get("campaign_id"), row.get("adset_id"))
