import os, re, requests, sys, collections
from google.ads.googleads.client import GoogleAdsClient

CODE = os.environ["AUTH_CODE"].strip()
m = re.search(r"code=([^&]+)", CODE)
if m: CODE = m.group(1)
CODE = requests.utils.unquote(CODE)
r = requests.post("https://oauth2.googleapis.com/token", data={
    "code": CODE, "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
    "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
    "redirect_uri": "http://localhost", "grant_type": "authorization_code"}, timeout=30)
if r.status_code != 200:
    print("EXCHANGE_FAIL", r.status_code, r.text[:300]); sys.exit(1)
rt = r.json()["refresh_token"]; print("::add-mask::" + rt); print("exchange ok")

cfg = {"developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
       "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
       "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
       "refresh_token": rt,
       "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"], "use_proto_plus": True}
svc = GoogleAdsClient.load_from_dict(cfg).get_service("GoogleAdsService")
NAMES = {"8385977843": "jelenew-Q&M", "5188331105": "Jelenew Cycling-1"}
q = ("SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
     "campaign.maximize_conversion_value.target_roas, campaign_budget.resource_name, "
     "campaign_budget.amount_micros, campaign.labels FROM campaign WHERE campaign.status = 'ENABLED'")

data = []
for cid in [c.strip() for c in os.environ["GOOGLE_ADS_CUSTOMER_IDS"].split(",") if c.strip()]:
    labels = {r0.label.resource_name: r0.label.name
              for r0 in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label")}
    print(f"LABELS_IN_ACCOUNT|{NAMES.get(cid,cid)}|" + ";".join(sorted(labels.values())))
    for rr in svc.search(customer_id=cid, query=q):
        names = [labels.get(l, "?") for l in rr.campaign.labels]
        b = rr.campaign_budget.amount_micros / 1_000_000
        try: tro = float(rr.campaign.maximize_conversion_value.target_roas)
        except Exception: tro = 0.0
        data.append((NAMES.get(cid, cid), rr.campaign.name, rr.campaign.advertising_channel_type.name,
                     b, tro, rr.campaign_budget.resource_name, "^".join(names)))
        if any(x.lower().startswith("mai") or "mai" in x.lower() for x in names):
            print(f"MAIISH|{NAMES.get(cid,cid)}|{rr.campaign.advertising_channel_type.name}|{b:.2f}|{tro:.2f}|{names}|{rr.campaign.name}")

def agg(mode):
    groups = collections.defaultdict(lambda: [0, 0.0, {}, 0.0, 0.0, 0, 0])
    for acct, name, ch, b, tro, res, labs in data:
        tags = labs.split("^")
        if mode == "exact":
            is_mai = any(t.strip().lower() == "mai" for t in tags)
        else:
            is_mai = any("mai" in t.lower() for t in tags)
        g = "mai" if is_mai else "非mai"
        for scope in [(acct, g), ("TOTAL", g), (acct, "全部"), ("TOTAL", "全部")]:
            v = groups[scope]
            v[0] += 1; v[1] += b
            v[2][res] = max(v[2].get(res, 0), b)
            if tro > 0: v[3] += b; v[4] += b * tro; v[5] += 1
            else: v[6] += 1
    print(f"=== MODE={mode} ===")
    for k, v in sorted(groups.items()):
        w = v[4] / v[3] if v[3] else 0
        print(f"{mode}|{k[0]}|{k[1]}|{v[0]}|{sum(v[2].values()):.2f}|{len(v[2])}|{w:.4f}|{v[5]}|{v[6]}|{v[3]:.2f}")

agg("exact"); agg("contains")
