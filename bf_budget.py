import os, json, base64, datetime, collections, requests
from decimal import Decimal
from google.ads.googleads.client import GoogleAdsClient

GH = os.environ.get("GITHUB_TOKEN", ""); REPO = os.environ.get("GITHUB_REPOSITORY", "")
META_TOK = os.environ["META_ACCESS_TOKEN"]; V = os.environ.get("META_API_VERSION", "v20.0")
MB = f"https://graph.facebook.com/{V}"

META_ACC = [("QMDT", "750289240467952", []),
            ("销售三部", "5600626876733411", []),
            ("Jelenew+", "1614799860253372", ["tofu"])]
GCIDS = [c.strip() for c in os.environ.get("GOOGLE_ADS_CUSTOMER_IDS", "").split(",") if c.strip()]

def meta_get(path, params):
    p = dict(params); p["access_token"] = META_TOK
    for _ in range(10):
        r = requests.get(f"{MB}/{path}", params=p, timeout=60)
        if r.status_code != 200:
            raise RuntimeError(f"{path} {r.status_code} {r.text[:200]}")
        j = r.json()
        for row in j.get("data", []):
            yield row
        nxt = j.get("paging", {}).get("next")
        if not nxt:
            return
        p = None
        url = nxt
        r = requests.get(url, timeout=60); j = r.json()
        for row in j.get("data", []):
            yield row
        while j.get("paging", {}).get("next"):
            r = requests.get(j["paging"]["next"], timeout=60); j = r.json()
            for row in j.get("data", []):
                yield row

res = {"updated_utc": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "meta": {}, "google": {}}

for name, aid, excl in META_ACC:
    camp = aset = 0.0; n_c = n_a = 0
    for c in meta_get(f"act_{aid}/campaigns", {"fields": "name,daily_budget,effective_status", "limit": 200}):
        if c.get("effective_status") != "ACTIVE":
            continue
        nm = (c.get("name") or "").lower()
        if any(k in nm for k in excl):
            continue
        camp += float(c.get("daily_budget") or 0) / 100; n_c += 1
    for a in meta_get(f"act_{aid}/adsets", {"fields": "name,daily_budget,effective_status,campaign{name}", "limit": 500}):
        if a.get("effective_status") != "ACTIVE":
            continue
        nm = (a.get("campaign", {}) or {}).get("name", "").lower()
        if any(k in nm for k in excl):
            continue
        aset += float(a.get("daily_budget") or 0) / 100; n_a += 1
    res["meta"][name] = {"budget": round(camp + aset, 2), "campaign_level": round(camp, 2),
                         "adset_level": round(aset, 2), "campaigns": n_c, "adsets": n_a,
                         "excluded": excl}

cfg = {k: os.environ.get(k, "") for k in ["GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
        "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_LOGIN_CUSTOMER_ID"]}
if all(cfg.values()):
    client = GoogleAdsClient.load_from_dict({
        "developer_token": cfg["GOOGLE_ADS_DEVELOPER_TOKEN"], "client_id": cfg["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": cfg["GOOGLE_ADS_CLIENT_SECRET"], "refresh_token": cfg["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": cfg["GOOGLE_ADS_LOGIN_CUSTOMER_ID"], "use_proto_plus": True})
    svc = client.get_service("GoogleAdsService")
    gm = {"mai": 0.0, "nonmai": 0.0}; per = {}
    for cid in GCIDS:
        labels = {str(r.label.id): r.label.name for r in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label")}
        seen = {}; buckets = {"mai": 0.0, "nonmai": 0.0}; n = {"mai": 0, "nonmai": 0}
        for r in svc.search(customer_id=cid, query=(
                "SELECT campaign.id, campaign.status, campaign.labels, campaign_budget.resource_name, "
                "campaign_budget.amount_micros FROM campaign WHERE campaign.status = 'ENABLED'")):
            tags = [labels.get(x.split("/")[-1], "") for x in r.campaign.labels]
            key = r.campaign_budget.resource_name
            k = "mai" if "mai" in tags else "nonmai"
            if key in seen: continue
            seen[key] = True
            buckets[k] += float(Decimal(str(r.campaign_budget.amount_micros)) / Decimal(1_000_000)); n[k] += 1
        per[cid] = {"mai": round(buckets["mai"], 2), "nonmai": round(buckets["nonmai"], 2), "count": n}
        gm["mai"] += buckets["mai"]; gm["nonmai"] += buckets["nonmai"]
    res["google"] = {"mai": round(gm["mai"], 2), "nonmai": round(gm["nonmai"], 2), "per_account": per}
else:
    res["google"] = {"error": "missing google env"}

raw = json.dumps(res, ensure_ascii=False, indent=1)
print(raw)
if GH and REPO:
    url = f"https://api.github.com/repos/{REPO}/contents/bf_budget.json"
    h = {"Authorization": f"Bearer {GH}", "Accept": "application/vnd.github+json"}
    r = requests.get(url, headers=h, params={"ref": "main"}, timeout=30)
    body = {"message": f"bf budget {res['updated_utc']}",
            "content": base64.b64encode(raw.encode()).decode(), "branch": "main"}
    if r.status_code == 200: body["sha"] = r.json()["sha"]
    assert requests.put(url, headers=h, json=body, timeout=30).status_code in (200, 201)
