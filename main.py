from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s\n%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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
        "--morning-report",
        action="store_true",
        help="Generate and send Morning Report V1 without changing budget alert state.",
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


def update_account_state(state: dict[str, Any], snapshot: AccountBudgetSnapshot) -> None:
    state.setdefault("accounts", {})[snapshot.account.account_id] = {
        "name": snapshot.account.name,
        "alerting": snapshot.should_alert,
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
        "last_balance": str(snapshot.current_balance),
        "last_average_daily_spend": str(snapshot.average_daily_spend),
        "last_threshold": str(snapshot.threshold),
        "currency": snapshot.currency,
    }


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
            already_alerting = account_was_alerting(state, account.account_id)

            if snapshot.should_alert and not already_alerting:
                if dry_run:
                    logger.info("DRY RUN: would send Feishu alert for account %s.", account.name)
                else:
                    notifier.send_budget_alert(snapshot)
                alert_sent = True
            elif snapshot.should_alert and already_alerting:
                logger.info("Account %s is still below threshold. Skipping duplicate alert.", account.name)
            elif already_alerting:
                logger.info("Account %s recovered above threshold. Alert state has been reset.", account.name)

            update_account_state(state, snapshot)
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

        already_alerting = account_was_alerting(state, account.account_id)

        if snapshot.should_alert and not already_alerting:
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
        elif snapshot.should_alert and already_alerting:
            pass

        update_account_state(state, snapshot)

    save_state(STATE_FILE, state)

    if not alert_sent and not had_error:
        print("No alert needed")

    return 1 if had_error else 0


def run_morning_report() -> int:
    validate_config()

    try:
        report = build_morning_report(REPORT_ACCOUNTS, MetaMarketingAPI())
        FeishuWebhookClient().send_text(report)
    except (ValueError, MetaAPIError, FeishuError) as exc:
        print(f"Morning report failed: {exc}")
        return 1

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
    if args.morning_report:
        raise SystemExit(run_morning_report())
    raise SystemExit(run(dry_run=args.dry_run or DRY_RUN))
