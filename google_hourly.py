import os, json, base64, datetime, collections, requests
from decimal import Decimal
from zoneinfo import ZoneInfo
from google.ads.googleads.client import GoogleAdsClient

GH = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")

CFG_KEYS = ["GOOGLE_ADS_DEVELOPER_TOKEN","GOOGLE_ADS_CLIENT_ID","GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN","GOOGLE_ADS_LOGIN_CUSTOMER_ID"]

cfg = {k: os.environ[k] for k in CFG_KEYS if os.environ.get(k)}
missing = [k for k in CFG_KEYS if not os.environ.get(k)]
if missing:
    raise SystemExit("missing env: " + ", ".join(missing))
client_cfg = {
    "developer_token": cfg["GOOGLE_ADS_DEVELOPER_TOKEN"],
    "client_id": cfg["GOOGLE_ADS_CLIENT_ID"],
    "client_secret": cfg["GOOGLE_ADS_CLIENT_SECRET"],
    "refresh_token": cfg["GOOGLE_ADS_REFRESH_TOKEN"],
    "login_customer_id": cfg["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
    "use_proto_plus": True,
}
client = GoogleAdsClient.load_from_dict(client_cfg)
svc = client.get_service("GoogleAdsService")
CIDS = [c.strip() for c in os.environ.get("GOOGLE_ADS_CUSTOMER_IDS","").split(",") if c.strip()]


def micros(v):
    return float(Decimal(str(v)) / Decimal(1_000_000))


res = {"updated_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
       "accounts": {}, "rows": [], "errors": []}

agg = collections.defaultdict(lambda: {"mai": 0.0, "nonmai": 0.0})   # hour -> sums
per_account = {}

for cid in CIDS:
    try:
        tz, name = None, cid
        for row in svc.search(customer_id=cid, query="SELECT customer.time_zone, customer.descriptive_name FROM customer"):
            tz = row.customer.time_zone
            name = row.customer.descriptive_name
            break
        tzinfo = ZoneInfo(tz) if tz else ZoneInfo("America/Los_Angeles")
        day = datetime.datetime.now(tzinfo).date().isoformat()

        labels = {}
        for row in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label"):
            labels[str(row.label.id)] = row.label.name
        camp_mai = {}
        for row in svc.search(customer_id=cid, query="SELECT campaign.id, campaign.name, campaign.labels FROM campaign"):
            tags = [labels.get(ref.split("/")[-1], "") for ref in row.campaign.labels]
            camp_mai[str(row.campaign.id)] = ("mai" in tags)

        hours = collections.defaultdict(lambda: {"mai": 0.0, "nonmai": 0.0})
        q = f"""SELECT campaign.id, segments.hour, metrics.cost_micros
                FROM campaign
                WHERE segments.date = '{day}' AND metrics.cost_micros > 0
                ORDER BY segments.hour"""
        for batch in svc.search_stream(customer_id=cid, query=q):
            for row in batch.results:
                h = int(row.segments.hour)
                cost = micros(row.metrics.cost_micros)
                key = "mai" if camp_mai.get(str(row.campaign.id), False) else "nonmai"
                hours[h][key] += cost
        per_account[cid] = {"name": name, "tz": tz, "date": day,
                            "hours": {str(h): {"mai": round(v["mai"], 2), "nonmai": round(v["nonmai"], 2)}
                                      for h, v in sorted(hours.items())}}
        res["accounts"][cid] = {"name": name, "tz": tz, "date": day}
        for h, v in hours.items():
            agg[h]["mai"] += v["mai"]; agg[h]["nonmai"] += v["nonmai"]
    except Exception as exc:
        res["errors"].append({cid: f"{type(exc).__name__}: {exc}"})

res["per_account"] = per_account
res["rows"] = [{"hour": h, "mai": round(agg[h]["mai"], 2), "nonmai": round(agg[h]["nonmai"], 2)}
               for h in range(24)]
res["totals"] = {"mai": round(sum(v["mai"] for v in agg.values()), 2),
                 "nonmai": round(sum(v["nonmai"] for v in agg.values()), 2)}

raw = json.dumps(res, ensure_ascii=False, indent=1)
print(raw)

if GH and REPO:
    url = f"https://api.github.com/repos/{REPO}/contents/google_hourly.json"
    h = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
    sha = None
    r = requests.get(url, headers=h, params={"ref": "main"}, timeout=30)
    if r.status_code == 200:
        sha = r.json()["sha"]
    body = {"message": f"google hourly {res['updated_utc']}",
            "content": base64.b64encode(raw.encode()).decode(), "branch": "main"}
    if sha:
        body["sha"] = sha
    assert requests.put(url, headers=h, json=body, timeout=30).status_code in (200, 201), "push failed"
