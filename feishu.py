from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import requests

from config import FEISHU_WEBHOOK_URL, REQUEST_BACKOFF_SECONDS, REQUEST_MAX_RETRIES, REQUEST_TIMEOUT_SECONDS


logger = logging.getLogger(__name__)


class FeishuError(RuntimeError):
    pass


class FeishuWebhookClient:
    def __init__(self, webhook_url: str = FEISHU_WEBHOOK_URL) -> None:
        self.webhook_url = webhook_url
        self.session = requests.Session()

    def send_text(self, text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": text},
        }

        last_error: Exception | None = None
        for attempt in range(1, REQUEST_MAX_RETRIES + 1):
            try:
                response = self.session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                try:
                    result = response.json()
                except ValueError:
                    result = None
                if response.status_code >= 400:
                    raise FeishuError(
                        f"HTTP {response.status_code} body={response.text[:300]}"
                    )
                if result is not None and result.get("code") not in (0, None):
                    raise FeishuError(
                        f"feishu code={result.get('code')} "
                        f"msg={result.get('msg') or result.get('message')} body={result}"
                    )
                sent_at = datetime.now().astimezone().isoformat(timespec="seconds")
                delivery = {
                    "http_status": response.status_code,
                    "feishu_code": (result or {}).get("code"),
                    "feishu_message": (result or {}).get("msg") or (result or {}).get("message"),
                    "sent_at": sent_at,
                }
                logger.info(
                    "Feishu webhook sent | http_status=%s | feishu_code=%s | sent_at=%s",
                    delivery["http_status"], delivery["feishu_code"], sent_at,
                )
                return delivery
            except (requests.RequestException, ValueError, FeishuError) as exc:
                last_error = exc
                if attempt == REQUEST_MAX_RETRIES:
                    break

                sleep_seconds = REQUEST_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Feishu webhook request failed on attempt %s/%s: %s. Retrying in %.1fs.",
                    attempt,
                    REQUEST_MAX_RETRIES,
                    exc,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        detail = str(last_error) if last_error else "UnknownError"
        raise FeishuError(f"Feishu webhook request failed after retries: {detail}") from last_error
