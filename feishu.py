from __future__ import annotations

import logging
import time
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

    def send_text(self, text: str) -> None:
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
                response.raise_for_status()
                result = response.json()
                if result.get("code") not in (0, None):
                    raise FeishuError(f"Feishu webhook error: {result}")
                return
            except (requests.RequestException, ValueError, FeishuError) as exc:
                last_error = exc
                if attempt == REQUEST_MAX_RETRIES:
                    break

                sleep_seconds = REQUEST_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Feishu webhook request failed on attempt %s/%s. Retrying in %.1fs.",
                    attempt,
                    REQUEST_MAX_RETRIES,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        error_name = type(last_error).__name__ if last_error else "UnknownError"
        raise FeishuError(f"Feishu webhook request failed after retries: {error_name}") from last_error
