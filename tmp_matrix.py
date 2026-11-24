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

agg = collections.defaultdict(lambda: [0, 0.0, set(), 0.0, 0.0, 0, 0])
# value: [count, budget_sum, unique_budgets, sum_b, sum_b_troas, n_with_troas, n_without_troas]

for cid in [c.strip() for c in os.environ["GOOGLE_ADS_CUSTOMER_IDS"].split(",") if c.strip()]:
    labels = {}
    for r0 in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label"):
        labels[r0.label.resource_name] = r0.label.name
    rows = list(svc.search(customer_id=cid, query=q))
    acct = NAMES.get(cid, cid)
    print(f"ACCT|{acct}|{cid}|enabled={len(rows)}")
    for rr in rows:
        b = rr.campaign_budget.amount_micros / 1_000_000
        labs = [labels.get(l, "") for l in rr.campaign.labels]
        is_mai = any("mai" in x.lower() for x in labs)
        grp = "mai" if is_mai else "非mai"
        ch = rr.campaign.advertising_channel_type.name
        try: tro = float(rr.campaign.maximize_conversion_value.target_roas)
        except Exception: tro = 0.0
        for scope in [(acct, grp, ch), (acct, grp, "ALL"), (acct, "ALL", "ALL")]:
            v = agg[scope]
            v[0] += 1; v[1] += b; v[2].add(rr.campaign_budget.resource_name)
            if tro > 0:
                v[3] += b; v[4] += b * tro; v[5] += 1
            else:
                v[6] += 1
        print(f"ROW|{acct}|{grp}|{ch}|{b:.2f}|{tro:.4f}|{rr.campaign.name}")

print("== AGG ==")
for k, v in sorted(agg.items()):
    w = (v[4] / v[3]) if v[3] else 0.0
    print(f"AGG|{k[0]}|{k[1]}|{k[2]}|{v[0]}|{v[1]:.2f}|{len(v[2])}|{w:.4f}|{v[5]}|{v[6]}|{v[3]:.2f}")
