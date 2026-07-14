from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from config import (
    ACCOUNTS,
    DRY_RUN,
    FEISHU_WEBHOOK_URL,
    META_ACCESS_TOKEN,
    REPORT_ACCOUNTS,
    STATE_FILE,
    AdAccount,
    validate_config,
)
from feishu import FeishuError, FeishuWebhookClient
from meta_api import AccountBudgetSnapshot, MetaAPIError, MetaMarketingAPI
from morning_report import build_morning_report
from notifier import BudgetAlertNotifier, money
from scheduled_reports import run_scheduled_report
from skills.budget_manager import analyzer as budget_manager_analyzer
from skills.budget_manager import executor as budget_manager_executor


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s\n%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
DEBUG_LOG_FILE = Path("logs/budget_alert_debug.log")
REPEAT_ALERT_AFTER = timedelta(hours=24)


@dataclass(frozen=True)
class BudgetAlertDecision:
    previous_alert_state: bool
    trigger_by_days: bool
    trigger_by_amount: bool
    final_trigger: bool
    de_duplication_would_block: bool
    final_reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Meta ad account budget and send Feishu alerts.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use local sample data and print what would happen without calling Meta API or Feishu.",
    )
    parser.add_argument(
        "--notify-test",
        action="store_true",
        help="Send one Feishu connectivity test message without calling Meta API or checking budgets.",
    )
    parser.add_argument(
        "--meta-test",
        action="store_true",
        help="Read Meta account balance and spend without sending notifications or modifying state.",
    )
    parser.add_argument(
        "--check-budget",
        action="store_true",
        help="Read Meta data, check budget thresholds, send alerts only when needed, and update state.",
    )
    parser.add_argument(
        "--check-budget-debug",
        action="store_true",
        help="Print the budget-alert decision without sending Feishu or changing state.",
    )
    parser.add_argument(
        "--morning-report",
        action="store_true",
        help="Generate and send Morning Report V1 without changing budget alert state.",
    )
    parser.add_argument(
        "--budget-manager-preview",
        action="store_true",
        help="Scan Meta budgets and send a no-write Budget Manager preview.",
    )
    parser.add_argument(
        "--scheduled-report",
        choices=["morning", "daily-close", "early-pulse"],
        help="Send a concise scheduled Meta report for the selected slot.",
    )
    parser.add_argument(
        "--as-of",
        help="Optional ISO datetime for local scheduled-report testing, for example 2026-07-10T18:00:00-07:00.",
    )
    parser.add_argument(
        "--budget-manager-apply",
        metavar="RUN_ID",
        help="Apply a saved Budget Manager preview after exact APPLY confirmation.",
    )
    parser.add_argument(
        "--budget-manager-rollback",
        metavar="RUN_ID",
        help="Rollback the latest Budget Manager apply after exact ROLLBACK confirmation.",
    )
    return parser.parse_args()


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"accounts": {}}

    try:
        with path.open("r", encoding="utf-8") as file:
            state = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read state file %s. Starting with empty state. Error: %s", path, exc)
        return {"accounts": {}}

    if not isinstance(state, dict):
        return {"accounts": {}}
    state.setdefault("accounts", {})
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temp_path.replace(path)


def account_was_alerting(state: dict[str, Any], account_id: str) -> bool:
    account_state = state.get("accounts", {}).get(account_id, {})
    return bool(account_state.get("alerting"))


def account_last_alert_sent_at(state: dict[str, Any], account_id: str) -> datetime | None:
    raw = state.get("accounts", {}).get(account_id, {}).get("last_alert_sent_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def build_budget_alert_decision(snapshot: AccountBudgetSnapshot, state: dict[str, Any], now: datetime | None = None) -> BudgetAlertDecision:
    now = now or datetime.now()
    previous_alert_state = account_was_alerting(state, snapshot.account.account_id)
    last_sent = account_last_alert_sent_at(state, snapshot.account.account_id)
    trigger_by_days = snapshot.trigger_by_days
    trigger_by_amount = snapshot.trigger_by_amount
    raw_trigger = trigger_by_days or trigger_by_amount
    repeat_window_open = last_sent is None or now - last_sent >= REPEAT_ALERT_AFTER
    de_duplication_would_block = bool(raw_trigger and previous_alert_state and not repeat_window_open)

    if not raw_trigger:
        reason = "remaining_spend_limit is above threshold; no alert"
    elif de_duplication_would_block:
        reason = "below threshold but blocked by de-duplication; last alert was sent less than 24 hours ago"
    elif previous_alert_state and repeat_window_open:
        reason = "below threshold and 24-hour repeat window is open"
    else:
        reason = "below threshold and no active de-duplication block"

    return BudgetAlertDecision(
        previous_alert_state=previous_alert_state,
        trigger_by_days=trigger_by_days,
        trigger_by_amount=trigger_by_amount,
        final_trigger=raw_trigger and not de_duplication_would_block,
        de_duplication_would_block=de_duplication_would_block,
        final_reason=reason,
    )


def update_account_state(state: dict[str, Any], snapshot: AccountBudgetSnapshot, alert_sent: bool = False) -> None:
    previous = state.get("accounts", {}).get(snapshot.account.account_id, {})
    record = {
        "name": snapshot.account.name,
        "alerting": snapshot.should_alert,
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
        "last_balance": str(snapshot.current_balance),
        "last_average_daily_spend": str(snapshot.average_daily_spend),
        "last_threshold": str(snapshot.threshold),
        "balance_source": snapshot.balance_source,
        "account_spend_limit": str(snapshot.account_spend_limit),
        "amount_spent": str(snapshot.amount_spent),
        "currency": snapshot.currency,
    }
    if alert_sent:
        record["last_alert_sent_at"] = datetime.now().isoformat(timespec="seconds")
    elif previous.get("last_alert_sent_at") and snapshot.should_alert:
        record["last_alert_sent_at"] = previous["last_alert_sent_at"]
    state.setdefault("accounts", {})[snapshot.account.account_id] = record


def log_snapshot(snapshot: AccountBudgetSnapshot, alert_sent: bool) -> None:
    logger.info(
        "\n".join(
            [
                "Checking account:",
                snapshot.account.name,
                "",
                "Average Daily Spend:",
                f"{money(snapshot.average_daily_spend, snapshot.currency)}",
                "",
                "Current Balance:",
                f"{money(snapshot.current_balance, snapshot.currency)}",
                "",
                "Threshold:",
                f"{money(snapshot.threshold, snapshot.currency)}",
                "",
                "Alert:",
                "YES" if alert_sent else "NO",
            ]
        )
    )


def build_dry_run_snapshot(account: AdAccount, index: int) -> AccountBudgetSnapshot:
    seven_day_spend = Decimal("840.00") if index == 0 else Decimal("350.00")
    average_daily_spend = seven_day_spend / Decimal("7")
    current_balance = Decimal("250.00") if index == 0 else Decimal("260.00")
    threshold = average_daily_spend * Decimal("3")
    return AccountBudgetSnapshot(
        account=account,
        currency="USD",
        seven_day_spend=seven_day_spend,
        average_daily_spend=average_daily_spend,
        current_balance=current_balance,
        threshold=threshold,
        account_spend_limit=Decimal("1000.00"),
        amount_spent=Decimal("750.00") if index == 0 else Decimal("740.00"),
    )


def run(dry_run: bool = False) -> int:
    if not dry_run:
        validate_config()

    state = {"accounts": {}} if dry_run else load_state(STATE_FILE)
    meta_api = None if dry_run else MetaMarketingAPI()
    notifier = None if dry_run else BudgetAlertNotifier(FeishuWebhookClient())
    had_error = False

    if dry_run:
        logger.info("DRY RUN enabled. No Meta API requests or Feishu messages will be sent.")

    for index, account in enumerate(ACCOUNTS):
        alert_sent = False
        try:
            snapshot = (
                build_dry_run_snapshot(account, index)
                if dry_run
                else meta_api.get_budget_snapshot(account)
            )
            decision = build_budget_alert_decision(snapshot, state)

            if decision.final_trigger:
                if dry_run:
                    logger.info("DRY RUN: would send Feishu alert for account %s.", account.name)
                else:
                    notifier.send_budget_alert(snapshot)
                alert_sent = True
            elif decision.de_duplication_would_block:
                logger.info("Account %s is still below threshold. Skipping duplicate alert.", account.name)
            elif decision.previous_alert_state and not snapshot.should_alert:
                logger.info("Account %s recovered above threshold. Alert state has been reset.", account.name)

            update_account_state(state, snapshot, alert_sent)
            log_snapshot(snapshot, alert_sent)
        except Exception:
            had_error = True
            logger.exception("Failed to check account: %s (%s)", account.name, account.account_id)

    if dry_run:
        logger.info("DRY RUN complete. State file was not changed.")
    else:
        save_state(STATE_FILE, state)
    return 1 if had_error else 0


def run_notify_test() -> int:
    if not FEISHU_WEBHOOK_URL:
        logger.error("Missing required environment variable: FEISHU_WEBHOOK_URL")
        return 1

    try:
        FeishuWebhookClient().send_text("Meta Budget Alert\n\n飞书机器人连接成功。")
    except FeishuError as exc:
        logger.error("Feishu notify test failed: %s", exc)
        return 1

    logger.info("Feishu notify test sent successfully.")
    return 0


def run_meta_test() -> int:
    if not META_ACCESS_TOKEN:
        logger.error("Missing required environment variable: META_ACCESS_TOKEN")
        return 1

    api = MetaMarketingAPI()
    had_error = False

    for account in ACCOUNTS:
        print("---")
        print(f"Account Name: {account.name}")
        try:
            snapshot = api.get_budget_snapshot(account)
        except MetaAPIError as exc:
            had_error = True
            print(f"HTTP Status Code: {exc.http_status_code or 'unavailable'}")
            print(f"Meta Error Code: {exc.meta_error_code or 'unavailable'}")
            print(f"Error Message: {exc}")
            continue

        print(f"Current Balance: {money(snapshot.current_balance, snapshot.currency)}")
        print(f"Last 7 Days Spend: {money(snapshot.seven_day_spend, snapshot.currency)}")
        print(f"Average Daily Spend: {money(snapshot.average_daily_spend, snapshot.currency)}")

    return 1 if had_error else 0


def run_check_budget() -> int:
    validate_config()

    state = load_state(STATE_FILE)
    api = MetaMarketingAPI()
    notifier = BudgetAlertNotifier(FeishuWebhookClient())
    had_error = False
    alert_sent = False

    for account in ACCOUNTS:
        try:
            snapshot = api.get_budget_snapshot(account)
        except MetaAPIError as exc:
            had_error = True
            print("---")
            print(f"Account Name: {account.name}")
            print(f"HTTP Status Code: {exc.http_status_code or 'unavailable'}")
            print(f"Meta Error Code: {exc.meta_error_code or 'unavailable'}")
            print(f"Error Message: {exc}")
            continue

        decision = build_budget_alert_decision(snapshot, state)

        print("---")
        print(f"Account Name: {account.name}")
        print(f"Account ID: {account.account_id}")
        print(f"Currency: {snapshot.currency}")
        print(f"Balance Source: {snapshot.balance_source}")
        print(f"Account Spend Limit: {money(snapshot.account_spend_limit, snapshot.currency)}")
        print(f"Cumulative Amount Spent: {money(snapshot.amount_spent, snapshot.currency)}")
        print(f"Remaining Spend Limit: {money(snapshot.current_balance, snapshot.currency)}")
        print(f"Last 7 Days Spend: {money(snapshot.seven_day_spend, snapshot.currency)}")
        print(f"Average Daily Spend: {money(snapshot.average_daily_spend, snapshot.currency)}")
        print(f"Alert Threshold: {money(snapshot.threshold, snapshot.currency)}")
        print(f"Estimated Days Remaining: {snapshot.estimated_days_remaining:.2f}" if snapshot.estimated_days_remaining is not None else "Estimated Days Remaining: N/A")
        print(f"Previous Alert State: {'ALERTING' if decision.previous_alert_state else 'CLEAR'}")
        print(f"Trigger Result: {'TRUE' if decision.final_trigger else 'FALSE'}")

        if decision.final_trigger:
            try:
                notifier.send_budget_alert(snapshot)
            except FeishuError as exc:
                had_error = True
                print("---")
                print(f"Account Name: {account.name}")
                print(f"Error Message: {exc}")
                continue
            alert_sent = True
            print(f"Alert sent: {account.name}")
        else:
            print(f"Trigger Reason: {decision.final_reason}")

        update_account_state(state, snapshot, alert_sent)

    save_state(STATE_FILE, state)

    if not alert_sent and not had_error:
        print("No alert needed")

    return 1 if had_error else 0


def run_check_budget_debug() -> int:
    if not META_ACCESS_TOKEN:
        print("Missing required environment variable: META_ACCESS_TOKEN")
        return 1
    api = MetaMarketingAPI()
    state = load_state(STATE_FILE)
    had_error = False
    for account in ACCOUNTS:
        print("---")
        print(f"Account Name: {account.name}")
        print(f"Account ID: {account.account_id}")
        try:
            snapshot = api.get_budget_snapshot(account)
        except MetaAPIError as exc:
            had_error = True
            print("Data Status: ERROR")
            print(f"HTTP Status: {exc.http_status_code or 'unavailable'}")
            print(f"Meta Error Code: {exc.meta_error_code or 'unavailable'}")
            print(f"Error Message: {exc}")
            append_budget_alert_debug_log(
                {
                    "account_name": account.name,
                    "account_id": account.account_id,
                    "data_status": "ERROR",
                    "http_status": exc.http_status_code or "unavailable",
                    "meta_error_code": exc.meta_error_code or "unavailable",
                    "meta_error_message": str(exc),
                }
            )
            continue
        decision = build_budget_alert_decision(snapshot, state)
        print(f"Currency: {snapshot.currency}")
        print(f"account_spend_cap: {money(snapshot.account_spend_limit, snapshot.currency)}")
        print(f"amount_spent: {money(snapshot.amount_spent, snapshot.currency)}")
        print(f"remaining_spend_limit: {money(snapshot.current_balance, snapshot.currency)}")
        print(f"last_7_complete_days_spend: {money(snapshot.seven_day_spend, snapshot.currency)}")
        print(f"average_daily_spend: {money(snapshot.average_daily_spend, snapshot.currency)}")
        print(f"estimated_days_remaining: {snapshot.estimated_days_remaining:.2f}" if snapshot.estimated_days_remaining is not None else "estimated_days_remaining: N/A")
        print(f"threshold_days: {snapshot.threshold_days}")
        print(f"threshold_amount: {money(snapshot.threshold, snapshot.currency)}")
        print(f"previous_alert_state: {'ALERTING' if decision.previous_alert_state else 'CLEAR'}")
        print(f"trigger_by_days: {bool_text(decision.trigger_by_days)}")
        print(f"trigger_by_amount: {bool_text(decision.trigger_by_amount)}")
        print(f"final_trigger: {bool_text(decision.final_trigger)}")
        print(f"de_duplication_would_block: {bool_text(decision.de_duplication_would_block)}")
        print(f"final_reason: {decision.final_reason}")
        append_budget_alert_debug_log(debug_payload(snapshot, decision))
    print("Debug mode: no Feishu message sent; state.json unchanged")
    return 1 if had_error else 0


def bool_text(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def debug_payload(snapshot: AccountBudgetSnapshot, decision: BudgetAlertDecision) -> dict[str, Any]:
    return {
        "account_name": snapshot.account.name,
        "account_id": snapshot.account.account_id,
        "currency": snapshot.currency,
        "account_spend_cap": str(snapshot.account_spend_limit),
        "amount_spent": str(snapshot.amount_spent),
        "remaining_spend_limit": str(snapshot.current_balance),
        "last_7_complete_days_spend": str(snapshot.seven_day_spend),
        "average_daily_spend": str(snapshot.average_daily_spend),
        "estimated_days_remaining": str(snapshot.estimated_days_remaining) if snapshot.estimated_days_remaining is not None else None,
        "threshold_days": str(snapshot.threshold_days),
        "threshold_amount": str(snapshot.threshold),
        **asdict(decision),
    }


def append_budget_alert_debug_log(payload: dict[str, Any]) -> None:
    DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        key: value
        for key, value in payload.items()
        if key.lower() not in {"meta_access_token", "feishu_webhook_url", "authorization"}
        and "url" not in key.lower()
        and "token" not in key.lower()
        and "webhook" not in key.lower()
    }
    clean["created_at"] = datetime.now().isoformat(timespec="seconds")
    with DEBUG_LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(clean, ensure_ascii=False) + "\n")


def run_morning_report() -> int:
    validate_config()

    try:
        report = build_morning_report(REPORT_ACCOUNTS, MetaMarketingAPI())
        FeishuWebhookClient().send_text(report)
    except (ValueError, MetaAPIError, FeishuError) as exc:
        print(f"Morning report failed: {exc}")
        return 1

    if report.startswith("⚠️ Meta Morning Report 数据获取失败"):
        print("Morning report failure notice sent")
    else:
        print("Morning report sent")
    return 0


if __name__ == "__main__":
    args = parse_args()
    if args.notify_test:
        raise SystemExit(run_notify_test())
    if args.meta_test:
        raise SystemExit(run_meta_test())
    if args.check_budget:
        raise SystemExit(run_check_budget())
    if args.check_budget_debug:
        raise SystemExit(run_check_budget_debug())
    if args.morning_report:
        raise SystemExit(run_morning_report())
    if args.scheduled_report:
        raise SystemExit(run_scheduled_report(args.scheduled_report, args.as_of))
    if args.budget_manager_preview:
        budget_manager_analyzer.preview()
        raise SystemExit(0)
    if args.budget_manager_apply:
        raise SystemExit(budget_manager_executor.apply(args.budget_manager_apply))
    if args.budget_manager_rollback:
        raise SystemExit(budget_manager_executor.rollback(args.budget_manager_rollback))
    raise SystemExit(run(dry_run=args.dry_run or DRY_RUN))
