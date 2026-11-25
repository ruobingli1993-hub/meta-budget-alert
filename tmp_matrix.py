import os, re, requests, sys, collections
from google.ads.googleads.client import GoogleAdsClient

CODE = os.environ["AUTH_CODE"].strip()
m = re.search(r"code=([^&]+)", CODE)
if m: CODE = m.group(1)
CODE = requests.utils.unquote(CODE)

r = requests.post("https://oauth2.googleapis.com/token", data={
    "code": CODE,
    "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
    "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
    "redirect_uri": "http://localhost",
    "grant_type": "authorization_code",
}, timeout=30)
if r.status_code != 200:
    print("EXCHANGE_FAIL", r.status_code, r.text[:300]); sys.exit(1)
rt = r.json()["refresh_token"]
print("::add-mask::" + rt)
print("exchange ok")

cfg = {
    "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
    "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
    "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
    "refresh_token": rt,
    "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
    "use_proto_plus": True,
}
svc = GoogleAdsClient.load_from_dict(cfg).get_service("GoogleAdsService")
NAMES = {"8385977843": "jelenew-Q&M", "5188331105": "Jelenew Cycling-1"}

q = ("SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
     "campaign.bidding_strategy_type, campaign.maximize_conversion_value.target_roas, "
     "campaign_budget.resource_name, campaign_budget.amount_micros, campaign_budget.explicitly_shared, "
     "campaign.labels FROM campaign WHERE campaign.status = 'ENABLED'")

rows_all = []
for cid in [c.strip() for c in os.environ["GOOGLE_ADS_CUSTOMER_IDS"].split(",") if c.strip()]:
    labels = {r0.label.resource_name: r0.label.name
              for r0 in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label")}
    rows = list(svc.search(customer_id=cid, query=q))
    acct = NAMES.get(cid, cid)
    print(f"ACCT|{acct}|{cid}|enabled={len(rows)}")
    for rr in rows:
        b = rr.campaign_budget.amount_micros / 1_000_000
        labs = [labels.get(l, "") for l in rr.campaign.labels]
        grp = "mai" if any("mai" in x.lower() for x in labs) else "非mai"
        ch = rr.campaign.advertising_channel_type.name
        try: tro = float(rr.campaign.maximize_conversion_value.target_roas)
        except Exception: tro = 0.0
        rows_all.append((acct, grp, ch, b, tro, rr.campaign_budget.resource_name, rr.campaign.name))

for a, g, c, b, t, res, n in rows_all:
    print(f"ROW|{a}|{g}|{c}|{b:.2f}|{t:.4f}|{res}|{n}")

def report(scope_key, title):
    seen = {}
    cnt = 0; sum_raw = 0.0
    sb = 0.0; sbt = 0.0; nw = 0; nn = 0
    for a, g, c, b, t, res, n in rows_all:
        if scope_key(a, g, c):
            cnt += 1; sum_raw += b
            if res not in seen or seen[res] < b: seen[res] = b
            if t > 0: sb += b; sbt += b * t; nw += 1
            else: nn += 1
    dedup = sum(seen.values())
    w = (sbt / sb) if sb else 0.0
    print(f"AGG|{title}|{cnt}|{dedup:.2f}|{sum_raw:.2f}|{len(seen)}|{w:.4f}|{nw}|{nn}")

for acct in ["jelenew-Q&M", "Jelenew Cycling-1"]:
    for grp in ["mai", "非mai"]:
        for ch in ["SEARCH", "SHOPPING", "PERFORMANCE_MAX", "DEMAND_GEN", "DISPLAY", "VIDEO"]:
            if any(x[0] == acct and x[1] == grp and x[2] == ch for x in rows_all):
                report(lambda a, g, c, A=acct, G=grp, C=ch: a == A and g == G and c == C, f"{acct}|{grp}|{ch}")
        report(lambda a, g, c, A=acct, G=grp: a == A and g == G, f"{acct}|{grp}|ALL")
    report(lambda a, g, c, A=acct: a == A, f"{acct}|ALL|ALL")
report(lambda a, g, c: True, "TOTAL|ALL|ALL")
for grp in ["mai", "非mai"]:
    report(lambda a, g, c, G=grp: g == G, f"TOTAL|{grp}|ALL")
