# -*- coding: utf-8 -*-
"""GA4 Data API 只读封装：OAuth 刷新 + runReport。预警系统数据层。"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
GA4_BASE = "https://analyticsdata.googleapis.com/v1beta"


class GA4Error(RuntimeError):
    pass


def _env(key: str) -> str:
    value = os.getenv(key, "")
    if not value:
        raise GA4Error(f"Missing environment variable: {key}")
    return value


def get_access_token() -> str:
    data = urllib.parse.urlencode(
        {
            "client_id": _env("GA4_CLIENT_ID"),
            "client_secret": _env("GA4_CLIENT_SECRET"),
            "refresh_token": _env("GA4_REFRESH_TOKEN"),
            "grant_type": "refresh_token",
        }
    ).encode()
    req = urllib.request.Request(TOKEN_URL, data=data)
    try:
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except urllib.error.HTTPError as exc:
        raise GA4Error(f"GA4 token refresh failed: HTTP {exc.code}") from exc
    token = resp.get("access_token")
    if not token:
        raise GA4Error("GA4 token refresh returned no access_token")
    return token


def run_report(body: dict[str, Any]) -> dict[str, Any]:
    """调用 GA4 runReport。body 需含 dateRanges/dimensions/metrics。"""
    token = get_access_token()
    property_id = _env("GA4_PROPERTY_ID")
    url = f"{GA4_BASE}/properties/{property_id}:runReport"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        raw = urllib.request.urlopen(req, timeout=30).read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise GA4Error(f"GA4 runReport failed: HTTP {exc.code}: {detail}") from exc
    return json.loads(raw)


def hourly_event_counts(event_name: str, start_date: str, end_date: str) -> dict[str, int]:
    """按 dateHour 返回指定事件计数，key 形如 'YYYYMMDDHH'。"""
    body = {
        "dimensions": [{"name": "dateHour"}],
        "metrics": [{"name": "eventCount"}],
        "dateRanges": [{"startDate": start_date, "endDate": end_date}],
        "dimensionFilter": {
            "filter": {
                "fieldName": "eventName",
                "inListFilter": {"values": [event_name]},
            }
        },
    }
    resp = run_report(body)
    out: dict[str, int] = {}
    for row in resp.get("rows", []):
        key = row["dimensionValues"][0]["value"]
        out[key] = int(row["metricValues"][0]["value"])
    return out


def verify_connection() -> dict[str, Any]:
    """连通性自检：最近 7 天 session_start 事件名列表。"""
    body = {
        "dimensions": [{"name": "eventName"}],
        "metrics": [{"name": "eventCount"}],
        "dateRanges": [{"startDate": "7daysAgo", "endDate": "today"}],
        "limit": 30,
    }
    return run_report(body)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = verify_connection()
    print("GA4 connection OK, events:", len(result.get("rows", [])))
    for row in result.get("rows", [])[:8]:
        print(" ", row["dimensionValues"][0]["value"], row["metricValues"][0]["value"])
