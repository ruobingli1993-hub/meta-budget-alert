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
TAGS = ["jelenew", "mai"]

q = ("SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
     "campaign_budget.resource_name, campaign_budget.amount_micros, campaign_budget.explicitly_shared, "
     "campaign.labels FROM campaign WHERE campaign.status = 'ENABLED'")

agg = collections.defaultdict(lambda: [0, 0.0, set()])
for cid in [c.strip() for c in os.environ["GOOGLE_ADS_CUSTOMER_IDS"].split(",") if c.strip()]:
    labels = {}
    for r0 in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label"):
        labels[r0.label.resource_name] = r0.label.name
    rows = list(svc.search(customer_id=cid, query=q))
    print(f"ACCT|{cid}|{NAMES.get(cid,'')}|enabled_campaigns={len(rows)}")
    for rr in rows:
        b = rr.campaign_budget.amount_micros / 1_000_000
        labs = [labels.get(l, "") for l in rr.campaign.labels]
        hit = [t for t in TAGS if any(t in x.lower() for x in labs)]
        if not hit: continue
        st = rr.campaign.status.name
        ch = rr.campaign.advertising_channel_type.name
        for t in hit:
            k = (NAMES.get(cid, cid), t, ch)
            agg[k][0] += 1
            agg[k][1] += b
            agg[k][2].add(rr.campaign_budget.resource_name)
        print(f"ROW|{NAMES.get(cid,cid)}|{'/'.join(hit)}|{ch}|{b:.2f}|{rr.campaign.name}")
print("== AGG ==")
for k, v in sorted(agg.items(), key=lambda x: (x[0][0], x[0][1], -x[1][1])):
    print(f"AGG|{k[0]}|{k[1]}|{k[2]}|{v[0]}|{v[1]:.2f}|{len(v[2])}")
print("== TOTAL ==")
for t in TAGS:
    s = sum(v[1] for k, v in agg.items() if k[1] == t)
    c = sum(v[0] for k, v in agg.items() if k[1] == t)
    print(f"TOTAL|{t}|{c}|{s:.2f}")
