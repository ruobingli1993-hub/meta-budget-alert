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
q = ("SELECT campaign.name, campaign.advertising_channel_type, campaign.maximize_conversion_value.target_roas, "
     "campaign_budget.resource_name, campaign_budget.amount_micros, campaign.labels "
     "FROM campaign WHERE campaign.status = 'ENABLED'")

data = []
for cid in [c.strip() for c in os.environ["GOOGLE_ADS_CUSTOMER_IDS"].split(",") if c.strip()]:
    labels = {r0.label.resource_name: r0.label.name
              for r0 in svc.search(customer_id=cid, query="SELECT label.id, label.name FROM label")}
    for rr in svc.search(customer_id=cid, query=q):
        tags = [labels.get(l, "") for l in rr.campaign.labels]
        b = rr.campaign_budget.amount_micros / 1_000_000
        try: tro = float(rr.campaign.maximize_conversion_value.target_roas)
        except Exception: tro = 0.0
        is_mai = any(t.strip().lower() == "mai" for t in tags)
        data.append((NAMES.get(cid, cid), "mai" if is_mai else "非mai",
                     rr.campaign.advertising_channel_type.name, b, tro,
                     rr.campaign_budget.resource_name, rr.campaign.name, "^".join(tags)))

def rows_for(key):
    seen = {}; cnt = 0; raw = 0.0; sb = 0.0; sbt = 0.0; nw = nn = 0
    for a, g, ch, b, tro, res, name, tags in data:
        if key(a, g, ch):
            cnt += 1; raw += b
            seen[res] = max(seen.get(res, 0), b)
            if tro > 0: sb += b; sbt += b * tro; nw += 1
            else: nn += 1
    ded = sum(seen.values())
    w = sbt / sb if sb else 0.0
    return cnt, ded, raw, len(seen), w, nw, nn, sb

print("FIX|账户|分组|类型|条数|去重预算|按campaign相加|预算资源数|加权tROAS|有tROAS|无tROAS|覆盖预算")
def emit(a, g, ch, title):
    r_ = rows_for(lambda x, y, z, A=a, G=g, C=ch: x == A and y == G and (C is None or z == C))
    print(f"FIX|{title}|{r_[0]}|{r_[1]:.2f}|{r_[2]:.2f}|{r_[3]}|{r_[4]:.4f}|{r_[5]}|{r_[6]}|{r_[7]:.2f}")

for acct in ["jelenew-Q&M", "Jelenew Cycling-1"]:
    for grp in ["mai", "非mai"]:
        for ch in ["SEARCH", "SHOPPING", "PERFORMANCE_MAX", "DEMAND_GEN", "DISPLAY", "VIDEO"]:
            if any(x[0] == acct and x[1] == grp and x[2] == ch for x in data):
                emit(acct, grp, ch, f"{acct}|{grp}|{ch}")
        emit(acct, grp, None, f"{acct}|{grp}|全部")
    emit(acct, None, None, f"{acct}|全部|全部")
emit(None, None, None, "两账户合计|全部|全部")
for grp in ["mai", "非mai"]:
    emit(None, grp, None, f"两账户合计|{grp}|全部")
print("=== 被排除的 cancel mai 类标签 ===")
for a, g, ch, b, tro, res, name, tags in data:
    if g == "非mai" and any("cancel mai" in t.lower() for t in tags.split("^")):
        print(f"EXCLUDED|{a}|{ch}|{b:.2f}|{tags}|{name}")
