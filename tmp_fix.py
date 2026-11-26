import os, re, requests, sys
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
q = ("SELECT campaign.name, campaign.advertising_channel_type, campaign.maximize_conversion_value.target_roas, "
     "campaign_budget.resource_name, campaign_budget.amount_micros, campaign.labels "
     "FROM campaign WHERE campaign.status = 'ENABLED'")

data = []
for cid in [c.strip() for c in os.environ["GOOGLE_ADS_CUSTOMER_IDS"].split(",") if c.strip()]:
    lab = {r0.label.resource_name: r0.label.name
           for r0 in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label")}
    for rr in svc.search(customer_id=cid, query=q):
        tags = [lab.get(l, "") for l in rr.campaign.labels]
        b = rr.campaign_budget.amount_micros / 1_000_000
        try: tro = float(rr.campaign.maximize_conversion_value.target_roas)
        except Exception: tro = 0.0
        is_mai = any(t.strip().lower() == "mai" for t in tags)
        data.append((NAMES.get(cid, cid), "mai" if is_mai else "非mai",
                     rr.campaign.advertising_channel_type.name, b, tro,
                     rr.campaign_budget.resource_name, rr.campaign.name, "^".join(tags)))

def agg(pred):
    seen = {}; cnt = 0; raw = 0.0; sb = 0.0; sbt = 0.0; nw = nn = 0
    for a, g, ch, b, tro, res, name, tags in data:
        if not pred(a, g, ch): continue
        cnt += 1; raw += b
        seen[res] = max(seen.get(res, 0), b)
        if tro > 0: sb += b; sbt += b * tro; nw += 1
        else: nn += 1
    ded = sum(seen.values())
    return cnt, ded, raw, len(seen), (sbt / sb if sb else 0.0), nw, nn, sb

print("FIX|账户|分组|类型|条数|去重预算|按campaign相加|预算资源数|加权tROAS|有tROAS|无tROAS|覆盖预算")
def row(title, pred):
    x = agg(pred)
    print(f"FIX|{title}|{x[0]}|{x[1]:.2f}|{x[2]:.2f}|{x[3]}|{x[4]:.4f}|{x[5]}|{x[6]}|{x[7]:.2f}")

ACC = ["jelenew-Q&M", "Jelenew Cycling-1"]; GRP = ["mai", "非mai"]
CH = ["SEARCH", "SHOPPING", "PERFORMANCE_MAX", "DEMAND_GEN", "DISPLAY", "VIDEO", "MULTI_CHANNEL"]
for a in ACC:
    for g in GRP:
        for ch in CH:
            if any(d[0] == a and d[1] == g and d[2] == ch for d in data):
                row(f"{a}|{g}|{ch}", lambda x, y, z, A=a, G=g, C=ch: x == A and y == G and z == C)
        row(f"{a}|{g}|全部", lambda x, y, z, A=a, G=g: x == A and y == G)
    row(f"{a}|全部|全部", lambda x, y, z, A=a: x == A)
for g in GRP: row(f"两账户合计|{g}|全部", lambda x, y, z, G=g: y == G)
row("两账户合计|全部|全部", lambda x, y, z: True)
print("=== cancel mai 类标签（应归非mai） ===")
for a, g, ch, b, tro, res, name, tags in data:
    if any("cancel mai" in t.lower() for t in tags.split("^")):
        print(f"EXCLUDED|{a}|{g}|{ch}|{b:.2f}|{tags}|{name}")
